import asyncio
import json
import logging
from collections import defaultdict
from typing import Optional, Union, List

import discord
from discord.ext import commands, tasks
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")


class NymStickyModal(discord.ui.Modal):
    """Interactive Modal for entering multiline sticky messages with markdown headers."""

    def __init__(self, bot: commands.Bot, cog: "StickyCog", target_channel: discord.TextChannel):
        super().__init__(title="Set Sticky Notice")
        self.bot = bot
        self.cog = cog
        self.target_channel = target_channel

        self.add_item(
            discord.ui.InputText(
                label="Sticky Message Content",
                style=discord.InputTextStyle.paragraph,
                placeholder="Type your multiline sticky message here...\nUse # Title, ## Header, **bold**, or > quotes.",
                required=True,
                max_length=2000,
            )
        )

        self.add_item(
            discord.ui.InputText(
                label="Format as Rich Embed? (yes/no)",
                style=discord.InputTextStyle.short,
                placeholder="Type 'yes' to send inside a sleek embed, or 'no' for plain text.",
                required=False,
                default="no",
                max_length=5,
            )
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        message_text = self.children[0].value.strip()
        as_embed_str = self.children[1].value.strip().lower()
        as_embed = as_embed_str in ("yes", "y", "true", "1")

        sent_msg_id = None
        try:
            new_msg = await self.cog._send_sticky(self.target_channel, message_text, as_embed)
            sent_msg_id = new_msg.id
        except Exception:
            pass

        async with self.cog.channel_locks[self.target_channel.id]:
            await self.cog._set_sticky_data(
                channel_id=self.target_channel.id,
                guild_id=interaction.guild.id,
                message_text=message_text,
                is_embed=as_embed,
                last_id=sent_msg_id,
            )

        format_type = "Rich Embed" if as_embed else "Plain Text / Markdown"
        embed = EmbedBuilder.success(
            title="Sticky Message Configured",
            description=f"Sticky notice posted and active for {self.target_channel.mention}!\n\n"
                        f"• **Format:** `{format_type}`\n"
                        f"• **Content Preview:**\n>>> {message_text[:200]}" + ("..." if len(message_text) > 200 else ""),
        )
        await interaction.followup.send(embed=embed, ephemeral=True)


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

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json_str)
            except Exception as e:
                logger.warning(f"Upstash Redis set failed for sticky:{channel_id}: {e}")

    async def _delete_sticky_data(self, channel: discord.TextChannel) -> bool:
        """Remove sticky message from both SQLite DB and Upstash Redis, with channel history sweep."""
        key = f"sticky:{channel.id}"
        data = await self._get_sticky_data(channel.id)
        deleted = False

        if data:
            deleted = True
            last_id = data.get("last_id")
            if last_id:
                try:
                    old_msg = await channel.fetch_message(int(last_id))
                    await old_msg.delete()
                except Exception:
                    pass

        await self.bot.db.execute("DELETE FROM sticky_messages WHERE channel_id = ?", (channel.id,))

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.delete(key)
                await self.bot.upstash.set(key, json.dumps({"disabled": True}), ex_seconds=86400)
            except Exception as e:
                logger.warning(f"Upstash Redis delete failed for sticky:{channel.id}: {e}")

        # Fallback sweep for orphaned bot messages
        try:
            async for msg in channel.history(limit=15):
                if msg.author.id == self.bot.user.id:
                    if msg.embeds and any(kw in (msg.embeds[0].title or "") for kw in ["Configured", "Removed", "Sticky", "Active"]):
                        continue
                    try:
                        await msg.delete()
                        deleted = True
                        break
                    except Exception:
                        pass
        except Exception:
            pass

        return deleted

    async def _send_sticky(self, channel: discord.TextChannel, message_text: str, is_embed: bool) -> discord.Message:
        """Helper to post the sticky message as a clean embed or plain text."""
        if is_embed:
            embed = discord.Embed(
                description=message_text,
                color=EmbedBuilder.COLOR_NEKOTINA
            )
            return await channel.send(embed=embed)
        return await channel.send(message_text)

    # --- Consolidated Subcommand Group ---

    sticky = discord.SlashCommandGroup("sticky", "Sticky message engine controls.")

    @sticky.command(name="modal", description="Open multiline paragraph modal popup to set sticky notice with newlines & headers.")
    async def sticky_modal_slash(
        self,
        ctx: discord.ApplicationContext,
        channel: Optional[discord.TextChannel] = discord.Option(description="Target channel (Defaults to current channel)", default=None),
    ):
        """Slash command opening multiline modal popup."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

        target_ch = channel or ctx.channel
        modal = NymStickyModal(self.bot, self, target_ch)
        await ctx.send_modal(modal)

    @sticky.command(name="set", description="Set a sticky notice message for a channel.")
    async def sticky_set_slash(
        self,
        ctx: discord.ApplicationContext,
        message: str = discord.Option(description="The sticky notice message content"),
        channel: Optional[discord.TextChannel] = discord.Option(description="Target channel (Defaults to current channel)", default=None),
        as_embed: bool = discord.Option(description="Format sticky message as a rich embed?", default=False)
    ):
        """Slash command to set a sticky notice."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

        target_ch = channel or ctx.channel
        async with self.channel_locks[target_ch.id]:
            sent_msg_id = None
            try:
                new_msg = await self._send_sticky(target_ch, message, as_embed)
                sent_msg_id = new_msg.id
            except Exception:
                pass

            await self._set_sticky_data(
                channel_id=target_ch.id,
                guild_id=ctx.guild.id,
                message_text=message,
                is_embed=as_embed,
                last_id=sent_msg_id
            )

        format_type = "Rich Embed" if as_embed else "Plain Text"
        embed = EmbedBuilder.success(
            title="Sticky Message Set",
            description=f"Sticky message configured for {target_ch.mention}.\n\n"
                        f"**Format:** `{format_type}`\n"
                        f"**Notice:**\n>>> {message}"
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @sticky.command(name="remove", description="Remove the sticky message from a channel.")
    async def sticky_remove_slash(
        self,
        ctx: discord.ApplicationContext,
        channel: Optional[discord.TextChannel] = discord.Option(description="Target channel (Defaults to current channel)", default=None)
    ):
        """Slash command to remove a sticky message."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

        target_ch = channel or ctx.channel
        async with self.channel_locks[target_ch.id]:
            deleted = await self._delete_sticky_data(target_ch)

        if deleted:
            embed = EmbedBuilder.success(
                title="Sticky Message Removed",
                description=f"Sticky message removed from {target_ch.mention}."
            )
        else:
            embed = EmbedBuilder.warning(
                title="No Sticky Message",
                description=f"There was no active sticky message configured in {target_ch.mention}."
            )
        await ctx.respond(embed=embed, ephemeral=True)


    @sticky.command(name="list", description="List all active sticky messages in this server.")
    async def sticky_list_slash(self, ctx: discord.ApplicationContext):
        """Slash command listing all active sticky messages."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

        rows = await self.bot.db.fetch_all(
            "SELECT channel_id, message, is_embed FROM sticky_messages WHERE guild_id = ?",
            (ctx.guild.id,)
        )

        if not rows:
            embed = EmbedBuilder.warning("No Active Sticky Messages", "No channels currently have sticky messages in this server.")
            return await ctx.respond(embed=embed, ephemeral=True)

        lines = []
        for r in rows:
            ch = ctx.guild.get_channel(r["channel_id"])
            ch_str = ch.mention if ch else f"`ID: {r['channel_id']}`"
            fmt = "Embed" if r["is_embed"] else "Text"
            snippet = r["message"][:40] + "..." if len(r["message"]) > 40 else r["message"]
            lines.append(f"• {ch_str} (`{fmt}`): \"{snippet}\"")

        embed = EmbedBuilder.base(
            title="📌 Active Sticky Messages",
            description="\n".join(lines),
            color=EmbedBuilder.COLOR_NEKOTINA,
            author=ctx.author,
        )
        await ctx.respond(embed=embed, ephemeral=True)

    # --- Prefix Command Fallbacks ---

    @commands.command(name="sticky")
    async def sticky_prefix(self, ctx: commands.Context, *, message: str):
        """Prefix command fallback (!sticky <message> / !sticky -embed <message> / nym sticky <message>)."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ You need **Manage Channels** or **Administrator** permission.")

        is_embed = False
        message_clean = message.strip()

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
            sent_msg_id = None
            try:
                new_msg = await self._send_sticky(ctx.channel, message_clean, is_embed)
                sent_msg_id = new_msg.id
            except Exception:
                pass

            await self._set_sticky_data(
                channel_id=ctx.channel.id,
                guild_id=ctx.guild.id,
                message_text=message_clean,
                is_embed=is_embed,
                last_id=sent_msg_id
            )

        format_str = " (Rich Embed)" if is_embed else ""
        await ctx.send(f"✧ Sticky message protocol engaged{format_str}.")

    @commands.command(name="unsticky")
    async def unsticky_prefix(self, ctx: commands.Context):
        """Prefix command fallback (!unsticky / nym unsticky)."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ You need **Manage Channels** or **Administrator** permission.")

        async with self.channel_locks[ctx.channel.id]:
            deleted = await self._delete_sticky_data(ctx.channel)

        if deleted:
            await ctx.send("⌬ Sticky message removed from this channel.")
        else:
            await ctx.send("⚠️ No active sticky message found in this channel.")

    # --- Event Listener ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for new messages and re-posts the sticky notice at the bottom."""
        if message.author.bot or not message.guild:
            return

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

        if message.channel.last_message_id == last_id:
            return

        async with self.channel_locks[message.channel.id]:
            current_data = await self._get_sticky_data(message.channel.id)
            if not current_data or current_data.get("disabled"):
                return

            current_last_id = current_data.get("last_id")
            sticky_text = current_data.get("message")
            is_embed = current_data.get("is_embed", False)

            if not sticky_text:
                return

            # Re-check inside lock to eliminate race conditions
            if current_last_id and message.channel.last_message_id == current_last_id:
                return

            # Extra safety check: inspect the most recent message in channel history
            try:
                async for last_msg in message.channel.history(limit=1):
                    if last_msg.id == current_last_id or last_msg.author.id == self.bot.user.id:
                        return
            except Exception:
                pass

            if current_last_id:
                try:
                    old_msg = await message.channel.fetch_message(current_last_id)
                    await old_msg.delete()
                except Exception:
                    pass

            try:
                new_msg = await self._send_sticky(message.channel, sticky_text, is_embed)
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
