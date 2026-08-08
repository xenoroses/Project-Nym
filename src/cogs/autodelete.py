import asyncio
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Union, Literal

import discord
from discord.ext import commands, tasks
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")


def parse_duration_to_seconds(duration_str: str) -> Optional[int]:
    """
    Parses human-readable duration strings into seconds.
    Examples: '5m' -> 300, '1h' -> 3600, '24h' -> 86400, '1d' -> 86400, '1w' -> 604800, '0' -> 0.
    """
    duration_str = str(duration_str).strip().lower()
    if duration_str in ["0", "instant", "now"]:
        return 0
    if duration_str in ["off", "disable", "stop"]:
        return -1
    match = re.match(r"^(\d+)\s*([smhdw]?)$", duration_str)
    if not match:
        return None
    val, unit = int(match.group(1)), match.group(2)
    if not unit or unit == "s":
        return val
    elif unit == "m":
        return val * 60
    elif unit == "h":
        return val * 3600
    elif unit == "d":
        return val * 86400
    elif unit == "w":
        return val * 604800
    return None


def format_seconds_to_duration(seconds: int) -> str:
    if seconds == 0:
        return "Instant (On Send)"
    if seconds < 60:
        return f"{seconds} seconds"
    elif seconds < 3600:
        mins = seconds // 60
        return f"{mins} minute{'s' if mins > 1 else ''}"
    elif seconds < 86400:
        hrs = seconds // 3600
        return f"{hrs} hour{'s' if hrs > 1 else ''}"
    elif seconds < 604800:
        days = seconds // 86400
        return f"{days} day{'s' if days > 1 else ''}"
    else:
        weeks = seconds // 604800
        return f"{weeks} week{'s' if weeks > 1 else ''}"


class AutoDeleteCog(commands.Cog):
    """EazyAutodelete-Style High Performance Auto-Delete Engine for Project Nym.

    Supports automatic message cleanup based on custom time intervals (e.g. 5m, 1h, 24h, 1w),
    content filters (links, media, text, bots, humans, mentions), and dual-tier persistence.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queue_sweeper.start()

    def cog_unload(self):
        self.queue_sweeper.cancel()

    # --- Storage Helpers (Upstash Redis + SQLite) ---

    async def _get_channel_config(self, channel_id: int) -> Optional[dict]:
        """Fetch autodelete config for a channel from Redis or SQLite."""
        key = f"autodelete:config:{channel_id}"

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                raw_data = await self.bot.upstash.get(key)
                if raw_data:
                    parsed = json.loads(raw_data)
                    if isinstance(parsed, dict):
                        if parsed.get("disabled"):
                            return None
                        return parsed
            except Exception as e:
                logger.warning(f"Upstash read failed for autodelete config {channel_id}: {e}")

        try:
            row = await self.bot.db.fetch_one(
                "SELECT * FROM autodelete_configs WHERE channel_id = ?",
                (channel_id,)
            )
            if row and row["enabled"]:
                data = {
                    "enabled": bool(row["enabled"]),
                    "duration_seconds": row["duration_seconds"],
                    "filter_mode": row["filter_mode"],
                    "exempt_pinned": bool(row["exempt_pinned"]),
                    "exempt_bots": bool(row["exempt_bots"]),
                    "exempt_admins": bool(row["exempt_admins"]),
                }
                if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
                    await self.bot.upstash.set(key, json.dumps(data))
                return data
        except Exception as e:
            logger.error(f"SQLite read error for autodelete config {channel_id}: {e}")

        return None

    async def _set_channel_config(
        self,
        channel_id: int,
        guild_id: int,
        duration_seconds: int,
        filter_mode: str = "all"
    ) -> None:
        """Save autodelete configuration to SQLite DB and Upstash Redis."""
        key = f"autodelete:config:{channel_id}"
        data = {
            "enabled": True,
            "duration_seconds": duration_seconds,
            "filter_mode": filter_mode,
            "exempt_pinned": True,
            "exempt_bots": True,
            "exempt_admins": True,
        }

        await self.bot.db.execute(
            """
            INSERT INTO autodelete_configs (channel_id, guild_id, enabled, duration_seconds, filter_mode)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                enabled = 1,
                duration_seconds = excluded.duration_seconds,
                filter_mode = excluded.filter_mode
            """,
            (channel_id, guild_id, duration_seconds, filter_mode)
        )

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json.dumps(data))
            except Exception as e:
                logger.warning(f"Upstash set failed for autodelete config {channel_id}: {e}")

    async def _disable_channel_config(self, channel_id: int) -> None:
        """Disable autodelete for a channel in SQLite DB and Upstash Redis."""
        key = f"autodelete:config:{channel_id}"

        await self.bot.db.execute(
            "UPDATE autodelete_configs SET enabled = 0 WHERE channel_id = ?",
            (channel_id,)
        )

        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                await self.bot.upstash.set(key, json.dumps({"disabled": True}), ex_seconds=86400)
            except Exception as e:
                logger.warning(f"Upstash delete failed for autodelete config {channel_id}: {e}")

    def _should_delete_message(self, message: discord.Message, config: dict) -> bool:
        """Evaluate if a message matches configured filter rules."""
        if not config.get("enabled"):
            return False

        if config.get("exempt_pinned", True) and message.pinned:
            return False

        if message.author.bot and config.get("exempt_bots", True):
            return False

        if isinstance(message.author, discord.Member) and config.get("exempt_admins", True):
            if message.author.guild_permissions.administrator or message.author.guild_permissions.manage_guild:
                return False

        fmode = config.get("filter_mode", "all")
        content = message.content or ""

        if fmode == "all":
            return True
        elif fmode == "links":
            return bool(re.search(r"http[s]?://", content))
        elif fmode == "media":
            return len(message.attachments) > 0 or len(message.embeds) > 0
        elif fmode == "text":
            return len(message.attachments) == 0 and len(message.embeds) == 0 and not bool(re.search(r"http[s]?://", content))
        elif fmode == "bots":
            return message.author.bot
        elif fmode == "humans":
            return not message.author.bot
        elif fmode == "mentions":
            return bool(message.mentions or message.role_mentions or message.mention_everyone)

        return True

    # --- Consolidated Subcommand Group ---

    autodelete = discord.SlashCommandGroup("autodelete", "EazyAutodelete channel message cleanup controls.")

    @autodelete.command(name="set", description="Configure automatic message deletion for this channel.")
    async def autodelete_set(
        self,
        ctx: discord.ApplicationContext,
        duration: str = discord.Option(description="Duration (e.g. 5m, 1h, 24h, 1w, 0 for instant, off to stop)"),
        channel: Optional[discord.TextChannel] = discord.Option(description="Target channel (Defaults to current channel)", default=None),
        filter_mode: str = discord.Option(
            description="Content filter type",
            choices=["all", "links", "media", "text", "bots", "humans", "mentions"],
            default="all"
        )
    ):
        """Set up autodelete duration and filter for a channel."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

        target_ch = channel or ctx.channel
        seconds = parse_duration_to_seconds(duration)

        if seconds is None:
            embed = EmbedBuilder.error(
                "Invalid Duration",
                "Please specify a valid duration string.\nExamples: `5m`, `1h`, `24h`, `1d`, `1w`, `0` (instant), `off`."
            )
            return await ctx.respond(embed=embed, ephemeral=True)

        if seconds == -1:
            await self._disable_channel_config(target_ch.id)
            embed = EmbedBuilder.success(
                "AutoDelete Disabled",
                f"⌬ AutoDelete protocol disengaged for {target_ch.mention}."
            )
            return await ctx.respond(embed=embed, ephemeral=True)

        await self._set_channel_config(
            channel_id=target_ch.id,
            guild_id=ctx.guild.id,
            duration_seconds=seconds,
            filter_mode=filter_mode
        )

        dur_text = format_seconds_to_duration(seconds)
        embed = EmbedBuilder.success(
            "AutoDelete Configured",
            f"AutoDelete configured for {target_ch.mention}.\n\n"
            f"**Interval:** `{dur_text}`\n"
            f"**Filter Mode:** `{filter_mode.upper()}`\n"
            f"**Protections:** Pinned messages, bot posts, and admins are preserved."
        )
        await ctx.respond(embed=embed, ephemeral=True)

    @autodelete.command(name="off", description="Turn off automatic message deletion in a channel.")
    async def autodelete_off(
        self,
        ctx: discord.ApplicationContext,
        channel: Optional[discord.TextChannel] = discord.Option(description="Target channel (Defaults to current channel)", default=None)
    ):
        """Disable autodelete in a channel."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.respond("❌ You need **Manage Channels** or **Administrator** permission.", ephemeral=True)

        target_ch = channel or ctx.channel
        await self._disable_channel_config(target_ch.id)

        embed = EmbedBuilder.success(
            "AutoDelete Disabled",
            f"AutoDelete disabled for {target_ch.mention}."
        )
        await ctx.respond(embed=embed, ephemeral=True)


    @autodelete.command(name="status", description="Check active autodelete configuration for a channel.")
    async def autodelete_status(
        self,
        ctx: discord.ApplicationContext,
        channel: Optional[discord.TextChannel] = discord.Option(description="Target channel (Defaults to current channel)", default=None)
    ):
        """Show active autodelete status for a channel."""
        target_ch = channel or ctx.channel
        config = await self._get_channel_config(target_ch.id)

        if not config or not config.get("enabled"):
            embed = EmbedBuilder.warning(
                "AutoDelete Inactive",
                f"No active AutoDelete configuration found for {target_ch.mention}."
            )
            return await ctx.respond(embed=embed, ephemeral=True)

        dur_text = format_seconds_to_duration(config.get("duration_seconds", 3600))
        filter_mode = config.get("filter_mode", "all")

        embed = EmbedBuilder.base(
            title=f"⚙️ AutoDelete Telemetry — #{target_ch.name}",
            description=f"Active cleanup configuration for {target_ch.mention}.",
            color=EmbedBuilder.COLOR_NEKOTINA,
            author=ctx.author
        )
        embed.add_field(name="🌐 Status", value="`ACTIVE` ✅", inline=True)
        embed.add_field(name="⏱️ Interval", value=f"`{dur_text}`", inline=True)
        embed.add_field(name="🔍 Filter Mode", value=f"`{filter_mode.upper()}`", inline=True)
        embed.add_field(name="🛡️ Exemptions", value="`Pinned`, `Bots`, `Administrators`", inline=False)

        await ctx.respond(embed=embed, ephemeral=True)

    # --- Prefix Commands Fallback ---

    @commands.command(name="autodelete", aliases=["autoclean", "ad"])
    async def autodelete_prefix(self, ctx: commands.Context, duration: str = "status", filter_mode: str = "all"):
        """Prefix command fallback (!autodelete <duration> [filter] / nym autodelete <duration>)."""
        if not ctx.author.guild_permissions.manage_channels and not ctx.author.guild_permissions.administrator:
            return await ctx.send("❌ You need **Manage Channels** or **Administrator** permission.")

        duration_clean = duration.strip().lower()

        if duration_clean == "status":
            config = await self._get_channel_config(ctx.channel.id)
            if not config or not config.get("enabled"):
                return await ctx.send(f"⚠️ AutoDelete is currently **inactive** in {ctx.channel.mention}.")
            dur_text = format_seconds_to_duration(config.get("duration_seconds", 3600))
            return await ctx.send(f"⚙️ AutoDelete in {ctx.channel.mention} is **Active** (`{dur_text}`, Filter: `{config.get('filter_mode', 'all').upper()}`).")

        seconds = parse_duration_to_seconds(duration_clean)
        if seconds is None:
            return await ctx.send("❌ Invalid duration. Example usage: `!autodelete 1h` or `!autodelete 5m links` or `!autodelete off`.")

        if seconds == -1:
            await self._disable_channel_config(ctx.channel.id)
            return await ctx.send(f"⌬ AutoDelete disabled for {ctx.channel.mention}.")

        await self._set_channel_config(
            channel_id=ctx.channel.id,
            guild_id=ctx.guild.id,
            duration_seconds=seconds,
            filter_mode=filter_mode
        )
        dur_text = format_seconds_to_duration(seconds)
        await ctx.send(f"✧ AutoDelete active in {ctx.channel.mention} (`{dur_text}`, Filter: `{filter_mode.upper()}`).")

    # --- Event Listener & Background Sweeper ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Queue or instantly delete messages matching channel autodelete rules."""
        if not message.guild or message.author.bot:
            return

        content = message.content.strip().lower()
        if content.startswith("!") or content.startswith("nym ") or content.startswith("/"):
            return

        config = await self._get_channel_config(message.channel.id)
        if not config or not self._should_delete_message(message, config):
            return

        duration_seconds = config.get("duration_seconds", 3600)

        if duration_seconds == 0:
            try:
                await message.delete()
            except Exception:
                pass
            return

        delete_at = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
        try:
            await self.bot.db.execute(
                """
                INSERT OR IGNORE INTO autodelete_queue (message_id, channel_id, guild_id, delete_at)
                VALUES (?, ?, ?, ?)
                """,
                (message.id, message.channel.id, message.guild.id, delete_at.isoformat())
            )
        except Exception as e:
            logger.error(f"Failed to queue message {message.id} for autodelete: {e}")

    @tasks.loop(seconds=10)
    async def queue_sweeper(self):
        """Background sweeper deleting expired messages from the queue every 10 seconds."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            rows = await self.bot.db.fetch_all(
                "SELECT message_id, channel_id FROM autodelete_queue WHERE delete_at <= ? LIMIT 50",
                (now_iso,)
            )
            if not rows:
                return

            for row in rows:
                msg_id = row["message_id"]
                ch_id = row["channel_id"]

                channel = self.bot.get_channel(ch_id)
                if channel:
                    try:
                        msg = await channel.fetch_message(msg_id)
                        await msg.delete()
                    except (discord.NotFound, discord.Forbidden):
                        pass
                    except Exception as e:
                        logger.warning(f"Failed deleting autodelete msg {msg_id}: {e}")

                await self.bot.db.execute(
                    "DELETE FROM autodelete_queue WHERE message_id = ?",
                    (msg_id,)
                )
        except Exception as e:
            logger.error(f"Error in autodelete queue sweeper: {e}")

    @queue_sweeper.before_loop
    async def before_sweeper(self):
        await self.bot.wait_until_ready()


def setup(bot: commands.Bot):
    bot.add_cog(AutoDeleteCog(bot))
