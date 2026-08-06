import asyncio
import json
import logging
from collections import defaultdict
from typing import Optional, Union
import discord
from discord.ext import commands, tasks
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")


class StickyCog(commands.Cog):
    """Premium Sticky Message Engine.

    Ensures persistent visibility of critical channel notices even in high-traffic channels.
    Supports dual-tier caching (Upstash Redis + SQLite database persistence) and optional rich embed formatting.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_locks = defaultdict(asyncio.Lock)
        self.prune_trackers.start()

    def cog_unload(self):
        self.prune_trackers.cancel()

    @tasks.loop(hours=24)
    async def prune_trackers(self):
        """Clean up stale channel locks every 24 hours."""
        for channel_id in list(self.channel_locks.keys()):
            if not self.bot.get_channel(channel_id):
                del self.channel_locks[channel_id]

    # --- Storage Helpers (Upstash Redis + SQLite) ---

    async def _get_sticky_data(self, channel_id: int) -> Optional[dict]:
        """Fetch sticky message data from Upstash Redis or SQLite fallback."""
        key = f"sticky:{channel_id}"

        # 1. Try Upstash Redis
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                raw_data = await self.bot.upstash.get(key)
                if raw_data:
                    parsed = json.loads(raw_data)
                    if isinstance(parsed, dict):
                        if parsed.get("disabled"):
                            return None
                        if parsed.get("message"):
                            return parsed
                    return None
            except Exception as e:
                logger.warning(f"Upstash Redis read failed for sticky:{channel_id}: {e}")

        # 2. Fallback to SQLite DB
        try:
            row = await self.bot.db.fetch_one(
                "SELECT message, is_embed, last_message_id FROM sticky_messages WHERE channel_id = ?",
                (channel_id,)
            )
            if row and row["message"]:
                is_embed = bool(row["is_embed"]) if "is_embed" in row.keys() and row["is_embed"] else False
                data = {
                    "message": row["message"],
                    "is_embed": is_embed,
                    "last_id": row["last_message_id"]
                }
                # Warm up Upstash cache if available
                if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
                    await self.bot.upstash.set(key, json.dumps(data))
                return data
        except Exception as e:
            logger.error(f"SQLite read error for sticky:{channel_id}: {e}")

        return None

    async def _set_sticky_data(
        self,
        channel_id: int,
        guild_id: int,
        message_text: str,
        is_embed: bool = False,
        last_id: Optional[int] = None
    ) -> None:
        """Save sticky message data to both SQLite DB and Upstash Redis."""
        key = f"sticky:{channel_id}"
        data = {
            "message": message_text,
            "is_embed": is_embed,
            "last_id": last_id
        }
        json_str = json.dumps(data)

        # 1. Save to SQLite
        await self.bot.db.execute(
            """
            INSERT INTO sticky_messages (channel_id, guild_id, message, is_embed, last_message_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                message = excluded.message,
                is_embed = excluded.is_embed,
                last_message_id = excluded.last_message_id
            """,
            (channel_id, guild_id, message_text, 1 if is_embed else 0, last_id)
        )

        # 2. Save to Upstash Redis
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json_str)
            except Exception as e:
                logger.warning(f"Upstash Redis set failed for sticky:{channel_id}: {e}")

    async def _delete_sticky_data(self, channel_id: int) -> None:
        """Remove sticky message from both SQLite DB and Upstash Redis."""
        key = f"sticky:{channel_id}"

        # Delete from SQLite
        await self.bot.db.execute("DELETE FROM sticky_messages WHERE channel_id = ?", (channel_id,))

        # Delete from Upstash Redis (set explicit disabled flag to bust any stale cache)
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.delete(key)
                await self.bot.upstash.set(key, json.dumps({"disabled": True}), ex_seconds=86400)
            except Exception as e:
                logger.warning(f"Upstash Redis delete failed for sticky:{channel_id}: {e}")

    async def _send_sticky(self, channel: discord.TextChannel, message_text: str, is_embed: bool) -> discord.Message:
        """Helper to post the sticky message as a clean embed or plain text."""
        if is_embed:
            embed = discord.Embed(
                description=message_text,
                color=EmbedBuilder.COLOR_NEKOTINA
            )
            return await channel.send(embed=embed)
        return await channel.send(message_text)


    # --- Commands ---

    @discord.slash_command(name="sticky", description="Set a sticky message for this channel.")
    async def sticky_slash(
        self,
        ctx: discord.ApplicationContext,
        message: str = discord.Option(description="The sticky notice message"),
        as_embed: bool = discord.Option(description="Format the sticky message as a rich embed?", default=False)
    ):
        """Slash command to set a sticky notice in the channel."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

        async with self.channel_locks[ctx.channel.id]:
            await self._set_sticky_data(
                channel_id=ctx.channel.id,
                guild_id=ctx.guild.id,
                message_text=message,
                is_embed=as_embed,
                last_id=None
            )

        format_type = "Rich Embed" if as_embed else "Plain Text"
        embed = EmbedBuilder.success(
            title="Sticky Message Set",
            description=f"✧ Sticky message protocol engaged for {ctx.channel.mention}.\n\n"
                        f"**Format:** `{format_type}`\n"
                        f"**Notice:**\n>>> {message}"
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(name="unsticky", description="Remove the sticky message from this channel.")
    async def unsticky_slash(self, ctx: discord.ApplicationContext):
        """Slash command to remove a sticky message from the channel."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

        async with self.channel_locks[ctx.channel.id]:
            data = await self._get_sticky_data(ctx.channel.id)

            if not data:
                embed = EmbedBuilder.warning(
                    title="No Sticky Message",
                    description="There is no active sticky message configured in this channel."
                )
                return await ctx.respond(embed=embed, ephemeral=True)

            last_id = data.get("last_id")
            await self._delete_sticky_data(ctx.channel.id)

            if last_id:
                try:
                    old_msg = await ctx.channel.fetch_message(last_id)
                    await old_msg.delete()
                except Exception:
                    pass

        embed = EmbedBuilder.success(
            title="Sticky Message Removed",
            description=f"⌬ Sticky message protocol disengaged for {ctx.channel.mention}."
        )
        await ctx.respond(embed=embed, ephemeral=True)


    # --- Prefix Command Fallbacks ---

    @commands.command(name="sticky")
    @commands.has_permissions(manage_channels=True)
    async def sticky_prefix(self, ctx: commands.Context, *, message: str):
        """Prefix command fallback (!sticky <message> / !sticky -embed <message> / nym sticky <message>)."""
        is_embed = False
        message_clean = message.strip()

        # Check for embed flags: -embed, --embed, or embed
        if message_clean.startswith("-embed "):
            is_embed = True
            message_clean = message_clean[7:].strip()
        elif message_clean.startswith("--embed "):
            is_embed = True
            message_clean = message_clean[8:].strip()
        elif message_clean.startswith("embed "):
            is_embed = True
            message_clean = message_clean[6:].strip()

        async with self.channel_locks[ctx.channel.id]:
            await self._set_sticky_data(
                channel_id=ctx.channel.id,
                guild_id=ctx.guild.id,
                message_text=message_clean,
                is_embed=is_embed,
                last_id=None
            )

        format_str = " (Rich Embed)" if is_embed else ""
        await ctx.send(f"✧ Sticky message protocol engaged{format_str}.")

    @commands.command(name="unsticky")
    @commands.has_permissions(manage_channels=True)
    async def unsticky_prefix(self, ctx: commands.Context):
        """Prefix command fallback (!unsticky / nym unsticky)."""
        async with self.channel_locks[ctx.channel.id]:
            data = await self._get_sticky_data(ctx.channel.id)
            if not data:
                return await ctx.send("⚠️ No active sticky message found in this channel.")

            last_id = data.get("last_id")
            await self._delete_sticky_data(ctx.channel.id)

            if last_id:
                try:
                    old_msg = await ctx.channel.fetch_message(last_id)
                    await old_msg.delete()
                except Exception:
                    pass

        await ctx.send("⌬ Sticky message removed from this channel.")

    # --- Event Listener ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for new messages and re-posts the sticky notice at the bottom."""
        if message.author.bot or not message.guild:
            return

        # Skip reposting if the message itself is a sticky/unsticky command invocation
        content_lower = message.content.lower().strip()
        if "unsticky" in content_lower or "sticky" in content_lower:
            return

        data = await self._get_sticky_data(message.channel.id)
        if not data or data.get("disabled"):
            return

        sticky_text = data.get("message")
        is_embed = data.get("is_embed", False)
        last_id = data.get("last_id")

        if not sticky_text:
            return

        # Avoid resending if the last message was already our sticky message
        if message.channel.last_message_id == last_id:
            return

        # Acquire lock per channel to prevent duplicate sticky posts
        async with self.channel_locks[message.channel.id]:
            # Re-fetch data inside lock to avoid double execution
            current_data = await self._get_sticky_data(message.channel.id)
            if not current_data or current_data.get("disabled"):
                return

            current_last_id = current_data.get("last_id")
            sticky_text = current_data.get("message")
            is_embed = current_data.get("is_embed", False)

            if not sticky_text:
                return

            # Delete previous sticky message
            if current_last_id:
                try:
                    old_msg = await message.channel.fetch_message(current_last_id)
                    await old_msg.delete()
                except Exception:
                    pass

            # Post new sticky message (Embed or Plain Text)
            try:
                new_msg = await self._send_sticky(message.channel, sticky_text, is_embed)

                # Update last_id
                await self._set_sticky_data(
                    channel_id=message.channel.id,
                    guild_id=message.guild.id,
                    message_text=sticky_text,
                    is_embed=is_embed,
                    last_id=new_msg.id
                )
            except Exception as e:
                logger.error(f"Failed to post sticky message in channel {message.channel.id}: {e}")


def setup(bot: commands.Bot):
    bot.add_cog(StickyCog(bot))
