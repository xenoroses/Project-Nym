import asyncio
import json
import logging
from collections import defaultdict
from typing import Optional, Union, List

import discord
from discord.ext import commands, tasks
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")

# Dual-library compatibility layer for Py-Cord and Discord.py v2
IS_PYCORD = hasattr(discord, "SlashCommandGroup")
if not IS_PYCORD:
    from discord import app_commands


class NymStickyModal(discord.ui.Modal):
    """Interactive Modal for entering multiline sticky messages with markdown headers."""

    def __init__(self, bot: commands.Bot, cog: "StickyCog", target_channel: discord.TextChannel):
        if IS_PYCORD:
            super().__init__(title="Set Sticky Notice")
        else:
            super().__init__(title="Set Sticky Notice")

        self.bot = bot
        self.cog = cog
        self.target_channel = target_channel

        if IS_PYCORD:
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
        else:
            self.msg_input = discord.ui.TextInput(
                label="Sticky Message Content",
                style=discord.TextStyle.paragraph,
                placeholder="Type your multiline sticky message here...\nUse # Title, ## Header, **bold**, or > quotes.",
                required=True,
                max_length=2000,
            )
            self.add_item(self.msg_input)
            self.embed_input = discord.ui.TextInput(
                label="Format as Rich Embed? (yes/no)",
                style=discord.TextStyle.short,
                placeholder="Type 'yes' to send inside a sleek embed, or 'no' for plain text.",
                required=False,
                default="no",
                max_length=5,
            )
            self.add_item(self.embed_input)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        message_text = self.children[0].value.strip()
        as_embed_str = self.children[1].value.strip().lower()
        as_embed = as_embed_str in ("yes", "y", "true", "1")

        async with self.cog.channel_locks[self.target_channel.id]:
            await self.cog._delete_sticky_data(self.target_channel)

            sent_msg_id = None
            try:
                new_msg = await self.cog._send_sticky(self.target_channel, message_text, as_embed)
                sent_msg_id = new_msg.id
            except Exception as e:
                logger.error(f"Failed sending initial sticky message from modal: {e}")

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

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(interaction)


class StickyCog(commands.Cog):
    """Premium Sticky Message Engine.

    Ensures persistent visibility of critical channel notices even in high-traffic channels.
    Supports dual-tier caching (Upstash Redis + SQLite database persistence) and optional rich embed formatting.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_locks = defaultdict(asyncio.Lock)
        self.sticky_cache = {}  # Fast RAM cache layer to shield Upstash Redis quota
        self.prune_trackers.start()

    def cog_unload(self):
        self.prune_trackers.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        """Pre-populate RAM cache from SQLite DB on startup to shield Upstash Redis quota."""
        try:
            rows = await self.bot.db.fetch_all("SELECT channel_id, message, is_embed, last_message_id FROM sticky_messages")
            if rows:
                for row in rows:
                    if row["message"]:
                        cid = int(row["channel_id"])
                        self.sticky_cache[cid] = {
                            "message": row["message"],
                            "is_embed": bool(row["is_embed"]),
                            "last_id": row["last_message_id"]
                        }
        except Exception as e:
            logger.warning(f"Failed pre-populating sticky RAM cache from SQLite: {e}")

    @tasks.loop(hours=24)
    async def prune_trackers(self):
        """Clean up stale channel locks every 24 hours."""
        for channel_id in list(self.channel_locks.keys()):
            if not self.bot.get_channel(channel_id):
                del self.channel_locks[channel_id]

    # --- Storage Helpers (SQLite DB -> Upstash Redis -> RAM Cache) ---

    async def _get_sticky_data(self, channel_id: int) -> Optional[dict]:
        """Fetch sticky message data with RAM Cache -> SQLite DB -> Upstash Redis fallback."""
        if channel_id in self.sticky_cache:
            cached = self.sticky_cache[channel_id]
            if not cached or cached.get("disabled") or not cached.get("message"):
                return None
            return cached

        # SQLite DB primary check (shields against Redis quota limits)
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
                self.sticky_cache[channel_id] = data
                return data
        except Exception as e:
            logger.error(f"SQLite read error for sticky:{channel_id}: {e}")

        key = f"nym:sticky:{channel_id}"
        legacy_key = f"sticky:{channel_id}"

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                raw_data = await self.bot.upstash.get(key) or await self.bot.upstash.get(legacy_key)
                if raw_data:
                    parsed = json.loads(raw_data)
                    if isinstance(parsed, str):
                        try: parsed = json.loads(parsed)
                        except Exception: pass
                    if isinstance(parsed, dict):
                        if parsed.get("disabled") or not parsed.get("message"):
                            self.sticky_cache[channel_id] = {"disabled": True, "message": None}
                            return None
                        self.sticky_cache[channel_id] = parsed
                        return parsed
            except Exception as e:
                logger.warning(f"Upstash Redis read failed for sticky:{channel_id}: {e}")

        self.sticky_cache[channel_id] = {"disabled": True, "message": None}
        return None

    async def _set_sticky_data(
        self,
        channel_id: int,
        guild_id: int,
        message_text: str,
        is_embed: bool = False,
        last_id: Optional[int] = None
    ) -> None:
        """Save sticky message data to RAM Cache, SQLite DB, and Upstash Redis."""
        key = f"nym:sticky:{channel_id}"
        legacy_key = f"sticky:{channel_id}"
        data = {
            "message": message_text,
            "is_embed": is_embed,
            "last_id": last_id
        }
        self.sticky_cache[channel_id] = data
        json_str = json.dumps(data)

        try:
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
        except Exception as e:
            logger.error(f"SQLite write error for sticky:{channel_id}: {e}")

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json_str)
                await self.bot.upstash.set(legacy_key, json.dumps({"disabled": True, "message": None}))
            except Exception as e:
                logger.warning(f"Upstash Redis set failed for sticky:{channel_id}: {e}")

    async def _delete_sticky_data(self, channel: discord.TextChannel) -> bool:
        """Remove sticky message permanently from RAM Cache, SQLite DB, and Upstash Redis."""
        key = f"nym:sticky:{channel.id}"
        legacy_key = f"sticky:{channel.id}"

        cached_data = self.sticky_cache.get(channel.id)
        had_active_config = False
        target_last_id = None

        if cached_data and isinstance(cached_data, dict):
            if not cached_data.get("disabled") and cached_data.get("message"):
                had_active_config = True
                target_last_id = cached_data.get("last_id")

        try:
            row = await self.bot.db.fetch_one(
                "SELECT message, last_message_id FROM sticky_messages WHERE channel_id = ?",
                (channel.id,)
            )
            if row and row["message"]:
                had_active_config = True
                if not target_last_id:
                    target_last_id = row["last_message_id"]
        except Exception as e:
            logger.error(f"SQLite check error during sticky deletion: {e}")

        deleted_physical = False

        if target_last_id:
            try:
                old_msg = await channel.fetch_message(int(target_last_id))
                await old_msg.delete()
                deleted_physical = True
            except Exception:
                pass

        try:
            async for msg in channel.history(limit=30):
                if msg.author.id == self.bot.user.id:
                    if msg.embeds and any(kw in (msg.embeds[0].title or "") for kw in ["Configured", "Removed", "Sticky", "Active", "Portal"]):
                        continue
                    try:
                        await msg.delete()
                        deleted_physical = True
                    except Exception:
                        pass
        except Exception:
            pass

        disabled_payload = json.dumps({"disabled": True, "message": None})
        self.sticky_cache[channel.id] = {"disabled": True, "message": None}

        try:
            await self.bot.db.execute("DELETE FROM sticky_messages WHERE channel_id = ?", (channel.id,))
            await self.bot.db.execute("DELETE FROM sticky_messages WHERE channel_id = ?", (str(channel.id),))
        except Exception as e:
            logger.error(f"SQLite deletion error: {e}")

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, disabled_payload)
                await self.bot.upstash.set(legacy_key, disabled_payload)
                await self.bot.upstash.delete(key)
                await self.bot.upstash.delete(legacy_key)
            except Exception as e:
                logger.warning(f"Upstash Redis delete failed for sticky:{channel.id}: {e}")

        return had_active_config or deleted_physical

    async def _send_sticky(self, channel: discord.TextChannel, message_text: str, is_embed: bool) -> discord.Message:
        """Helper to post the sticky message as a clean embed or plain text."""
        if is_embed:
            title = None
            desc = message_text.strip()

            if desc.startswith("# ") or desc.startswith("## "):
                lines = desc.split("\n", 1)
                title = lines[0].lstrip("#").strip()
                desc = lines[1].strip() if len(lines) > 1 else ""

            embed = discord.Embed(
                title=title if title else None,
                description=desc if desc else None,
                color=EmbedBuilder.COLOR_NEKOTINA
            )
            return await channel.send(embed=embed)
        return await channel.send(message_text)

    # --- Slash Commands Group ---

    if IS_PYCORD:
        sticky = discord.SlashCommandGroup("sticky", "Sticky message engine controls.")

        @sticky.command(name="modal", description="Open multiline paragraph modal popup to set sticky notice with newlines & headers.")
        async def sticky_modal_slash(
            self,
            ctx: discord.ApplicationContext,
            channel: Optional[discord.TextChannel] = discord.Option(description="Target channel (Defaults to current channel)", default=None),
        ):
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
            if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
                return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

            target_ch = channel or ctx.channel
            async with self.channel_locks[target_ch.id]:
                await self._delete_sticky_data(target_ch)

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

        @sticky.command(name="unsticky", description="Remove the sticky notice message from a channel.")
        async def sticky_unsticky_slash(
            self,
            ctx: discord.ApplicationContext,
            channel: Optional[discord.TextChannel] = discord.Option(description="Target channel (Defaults to current channel)", default=None)
        ):
            await self.sticky_remove_slash(ctx, channel)

        @sticky.command(name="list", description="List all active sticky messages in this server.")
        async def sticky_list_slash(self, ctx: discord.ApplicationContext):
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

        @discord.slash_command(name="unsticky", description="Remove the sticky notice message from a channel.")
        async def standalone_unsticky_slash(
            self,
            ctx: discord.ApplicationContext,
            channel: Optional[discord.TextChannel] = discord.Option(description="Target channel (Defaults to current channel)", default=None)
        ):
            await self.sticky_remove_slash(ctx, channel)

    # --- Prefix Command Fallbacks ---

    @commands.command(name="sticky", aliases=["setsticky", "addsticky"])
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
            try:
                await ctx.message.delete()
            except Exception:
                pass

            await self._delete_sticky_data(ctx.channel)

            sent_msg_id = None
            try:
                new_msg = await self._send_sticky(ctx.channel, message_clean, is_embed)
                sent_msg_id = new_msg.id
            except Exception as e:
                logger.error(f"Failed to send sticky message in channel {ctx.channel.id}: {e}")

            await self._set_sticky_data(
                channel_id=ctx.channel.id,
                guild_id=ctx.guild.id,
                message_text=message_clean,
                is_embed=is_embed,
                last_id=sent_msg_id
            )

    @commands.command(name="unsticky", aliases=["removesticky", "delsticky", "rmsticky", "clearsticky", "nosticky"])
    async def unsticky_prefix(self, ctx: commands.Context):
        """Prefix command fallback (!unsticky / nym unsticky)."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ You need **Manage Channels** or **Administrator** permission.")

        async with self.channel_locks[ctx.channel.id]:
            deleted = await self._delete_sticky_data(ctx.channel)

        if deleted:
            await ctx.send("⌬ Sticky message removed from this channel.", delete_after=4.0)
        else:
            await ctx.send("⚠️ No active sticky message found in this channel.", delete_after=4.0)

    # --- Event Listener ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listens for new messages and re-posts the sticky notice at the bottom."""
        if message.author.bot or not message.guild:
            return

        content_lower = message.content.lower().strip()
        cmd_keywords = (
            "!sticky", "!unsticky", ",sticky", ",unsticky",
            "nym sticky", "nym unsticky", "hya sticky", "hya unsticky",
            "setsticky", "removesticky", "delsticky", "clearsticky", "nosticky"
        )
        if content_lower in ("sticky", "unsticky") or any(content_lower.startswith(kw) for kw in cmd_keywords):
            return

        data = await self._get_sticky_data(message.channel.id)
        if not data or data.get("disabled"):
            return

        sticky_text = data.get("message")
        is_embed = data.get("is_embed", False)
        last_id = data.get("last_id")

        if not sticky_text:
            return

        if last_id and message.channel.last_message_id == int(last_id):
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

            if current_last_id and message.channel.last_message_id == int(current_last_id):
                return

            try:
                async for past_msg in message.channel.history(limit=25):
                    if past_msg.author.id == self.bot.user.id and past_msg.id != message.id:
                        if past_msg.embeds and any(kw in (past_msg.embeds[0].title or "") for kw in ["Configured", "Removed", "Portal"]):
                            continue
                        try:
                            await past_msg.delete()
                        except Exception:
                            pass
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


async def setup(bot: commands.Bot):
    res = bot.add_cog(StickyCog(bot))
    if asyncio.iscoroutine(res):
        await res
