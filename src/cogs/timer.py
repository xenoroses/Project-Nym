import os
import re
import json
import time
import uuid
import asyncio
import logging
from typing import Optional, List, Any, Union

import discord
from discord.ext import commands, tasks

logger = logging.getLogger("Nym")

IS_PYCORD = hasattr(discord, "SlashCommandGroup")
if not IS_PYCORD:
    from discord import app_commands


def parse_time_string(time_str: str) -> Optional[int]:
    """Parse time duration strings like '5m', '10s', '1h30m', '45' into total seconds."""
    time_str = time_str.strip().lower()
    if not time_str:
        return None
    if time_str.isdigit():
        return int(time_str) * 60

    pattern = re.compile(r'(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?')
    match = pattern.fullmatch(time_str)
    if not match or not any(match.groups()):
        return None

    days, hours, minutes, seconds = match.groups()
    total = 0
    if days: total += int(days) * 86400
    if hours: total += int(hours) * 3600
    if minutes: total += int(minutes) * 60
    if seconds: total += int(seconds)
    return total if total > 0 else None


def build_timer_embed(label: str, end_timestamp: int, author_id: int, participants: List[int], is_expired: bool = False) -> discord.Embed:
    """Build clean, aesthetic timer embed with zero emojis or symbols as requested by user."""
    if is_expired:
        title = f"Timer Concluded: {label}"
        desc = f"Timer completed <t:{end_timestamp}:R>.\nHost: <@{author_id}>"
    else:
        title = f"Timer: {label}"
        desc = (
            f"Time Remaining: <t:{end_timestamp}:R>\n"
            f"Ends: <t:{end_timestamp}:f>\n"
            f"Host: <@{author_id}>"
        )

    embed = discord.Embed(
        title=title,
        description=desc,
        color=0xFF69B4
    )

    p_count = len(participants)
    roster_str = ", ".join(f"<@{uid}>" for uid in participants) if p_count > 0 else "None yet"
    embed.add_field(name=f"Participants ({p_count})", value=roster_str, inline=False)
    return embed


class TimerButtonView(discord.ui.View):
    """Interactive Button View for joining or leaving a countdown timer."""

    def __init__(self, bot: commands.Bot, timer_id: str, disabled: bool = False):
        super().__init__(timeout=None)
        self.bot = bot
        self.timer_id = timer_id

        # Join/Leave Toggle Button
        button = discord.ui.Button(
            label="Join / Leave",
            style=discord.ButtonStyle.primary,
            custom_id=f"nym_timer_toggle:{timer_id}",
            disabled=disabled
        )
        button.callback = self.toggle_callback
        self.add_item(button)

    async def toggle_callback(self, interaction: discord.Interaction):
        cog: Optional["TimerCog"] = self.bot.get_cog("TimerCog")
        if not cog:
            try:
                if not interaction.response.is_done():
                    return await interaction.response.send_message("❌ Timer system is currently offline.", ephemeral=True)
            except Exception: pass
            return

        user_id = interaction.user.id
        updated_participants, timer_data = await cog.toggle_participant(self.timer_id, user_id)

        if timer_data is None:
            try:
                if not interaction.response.is_done():
                    return await interaction.response.send_message("⚠️ This timer has already expired or was removed.", ephemeral=True)
            except Exception: pass
            return

        is_joined = user_id in updated_participants
        status_msg = f"✨ You have **joined** the timer for **{timer_data['label']}**." if is_joined else f"ℹ️ You have **left** the timer for **{timer_data['label']}**."

        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(status_msg, ephemeral=True)
            else:
                await interaction.followup.send(status_msg, ephemeral=True)
        except Exception: pass

        # Update the original embed with updated roster
        try:
            channel = interaction.guild.get_channel(timer_data["channel_id"]) if interaction.guild else None
            if channel and timer_data.get("message_id"):
                msg = await channel.fetch_message(timer_data["message_id"])
                if msg:
                    new_embed = build_timer_embed(
                        label=timer_data["label"],
                        end_timestamp=int(timer_data["end_time"]),
                        author_id=timer_data["author_id"],
                        participants=updated_participants,
                        is_expired=False
                    )
                    await msg.edit(embed=new_embed, view=self)
        except Exception as e:
            logger.warning(f"Failed updating timer embed for {self.timer_id}: {e}")


class TimerCog(commands.Cog):
    """Aesthetic Countdown Timer Engine for Project Nym."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_tasks = {}
        self.timer_cache = {}

    @commands.Cog.listener()
    async def on_ready(self):
        """Resume active timers from SQLite DB on startup."""
        await asyncio.sleep(2)  # Wait for DB connection
        try:
            rows = await self.bot.db.fetch_all("SELECT timer_id, guild_id, channel_id, message_id, author_id, label, end_time, participants FROM active_timers")
            if rows:
                for row in rows:
                    t_id = row["timer_id"]
                    participants = json.loads(row["participants"]) if row["participants"] else []
                    t_data = {
                        "timer_id": t_id,
                        "guild_id": int(row["guild_id"]),
                        "channel_id": int(row["channel_id"]),
                        "message_id": int(row["message_id"]) if row["message_id"] else None,
                        "author_id": int(row["author_id"]),
                        "label": row["label"],
                        "end_time": float(row["end_time"]),
                        "participants": participants
                    }
                    self.timer_cache[t_id] = t_data

                    # Register persistent button view
                    view = TimerButtonView(self.bot, t_id)
                    self.bot.add_view(view)

                    # Resume countdown task if not already running
                    if t_id not in self.active_tasks:
                        task = asyncio.create_task(self._run_timer_countdown(t_id))
                        self.active_tasks[t_id] = task

                logger.info(f"Resumed {len(rows)} active countdown timer(s) from database.")
        except Exception as e:
            logger.warning(f"Failed resuming active timers on startup: {e}")

    async def toggle_participant(self, timer_id: str, user_id: int):
        """Toggle user participation in timer."""
        t_data = self.timer_cache.get(timer_id)
        if not t_data:
            # Fallback DB check
            try:
                row = await self.bot.db.fetch_one("SELECT timer_id, guild_id, channel_id, message_id, author_id, label, end_time, participants FROM active_timers WHERE timer_id = ?", (timer_id,))
                if row:
                    t_data = {
                        "timer_id": row["timer_id"],
                        "guild_id": int(row["guild_id"]),
                        "channel_id": int(row["channel_id"]),
                        "message_id": int(row["message_id"]) if row["message_id"] else None,
                        "author_id": int(row["author_id"]),
                        "label": row["label"],
                        "end_time": float(row["end_time"]),
                        "participants": json.loads(row["participants"]) if row["participants"] else []
                    }
                    self.timer_cache[timer_id] = t_data
            except Exception: pass

        if not t_data:
            return [], None

        participants = list(t_data.get("participants", []))
        if user_id in participants:
            participants.remove(user_id)
        else:
            participants.append(user_id)

        t_data["participants"] = participants
        self.timer_cache[timer_id] = t_data

        # Update DB
        try:
            await self.bot.db.execute("UPDATE active_timers SET participants = ? WHERE timer_id = ?", (json.dumps(participants), timer_id))
        except Exception as e:
            logger.error(f"Failed updating participants in DB for timer {timer_id}: {e}")

        return participants, t_data

    async def create_timer(self, channel: discord.TextChannel, author: Union[discord.User, discord.Member], duration_str: str, label: str) -> str:
        """Create and start a new countdown timer."""
        duration_sec = parse_time_string(duration_str)
        if not duration_sec or duration_sec < 5:
            raise ValueError("Invalid time duration. Examples: `5m`, `10s`, `1h`, `30`.")
        if duration_sec > 86400:
            raise ValueError("Timer duration cannot exceed 24 hours.")

        timer_id = str(uuid.uuid4())[:8]
        end_timestamp = int(time.time()) + duration_sec
        clean_label = label.strip()

        embed = build_timer_embed(
            label=clean_label,
            end_timestamp=end_timestamp,
            author_id=author.id,
            participants=[],
            is_expired=False
        )

        view = TimerButtonView(self.bot, timer_id)
        msg = await channel.send(embed=embed, view=view)

        t_data = {
            "timer_id": timer_id,
            "guild_id": channel.guild.id,
            "channel_id": channel.id,
            "message_id": msg.id,
            "author_id": author.id,
            "label": clean_label,
            "end_time": end_timestamp,
            "participants": []
        }
        self.timer_cache[timer_id] = t_data

        await self.bot.db.execute("""
            INSERT INTO active_timers (timer_id, guild_id, channel_id, message_id, author_id, label, end_time, participants)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (timer_id, channel.guild.id, channel.id, msg.id, author.id, clean_label, end_timestamp, "[]"))

        # Start background countdown task
        task = asyncio.create_task(self._run_timer_countdown(timer_id))
        self.active_tasks[timer_id] = task

        return timer_id

    async def _run_timer_countdown(self, timer_id: str):
        """Wait for timer expiration, trigger ghost pings, update embed, and clean up DB."""
        t_data = self.timer_cache.get(timer_id)
        if not t_data:
            return

        end_time = t_data["end_time"]
        remaining = end_time - time.time()
        if remaining > 0:
            await asyncio.sleep(remaining)

        # Refresh data from cache
        t_data = self.timer_cache.get(timer_id, t_data)
        guild_id = t_data["guild_id"]
        channel_id = t_data["channel_id"]
        message_id = t_data["message_id"]
        label = t_data["label"]
        author_id = t_data["author_id"]
        participants = t_data.get("participants", [])

        # Update Discord message & disable button
        guild = self.bot.get_guild(guild_id)
        if guild:
            channel = guild.get_channel(channel_id)
            if channel and message_id:
                try:
                    msg = await channel.fetch_message(message_id)
                    if msg:
                        expired_embed = build_timer_embed(
                            label=label,
                            end_timestamp=int(end_time),
                            author_id=author_id,
                            participants=participants,
                            is_expired=True
                        )
                        disabled_view = TimerButtonView(self.bot, timer_id, disabled=True)
                        await msg.edit(embed=expired_embed, view=disabled_view)
                except Exception as e:
                    logger.warning(f"Failed updating concluded timer embed {timer_id}: {e}")

                # Ghost Ping Notification for Participants
                if participants:
                    mentions = " ".join(f"<@{uid}>" for uid in participants)
                    ping_msg_text = f"{mentions} Timer for **{label}** has ended."
                    try:
                        ping_msg = await channel.send(ping_msg_text)
                        await asyncio.sleep(2.0)
                        await ping_msg.delete()
                    except Exception as e:
                        logger.warning(f"Failed sending ghost ping for timer {timer_id}: {e}")

        # Cleanup DB & RAM Cache
        if timer_id in self.timer_cache:
            del self.timer_cache[timer_id]
        if timer_id in self.active_tasks:
            del self.active_tasks[timer_id]

        try:
            await self.bot.db.execute("DELETE FROM active_timers WHERE timer_id = ?", (timer_id,))
        except Exception as e:
            logger.error(f"Failed deleting timer record {timer_id} from DB: {e}")

    # --- Slash Commands & Fallbacks ---

    if IS_PYCORD:
        @discord.slash_command(name="timer", description="Set an aesthetic countdown timer for games or events.")
        async def timer_slash(
            self,
            ctx: discord.ApplicationContext,
            time_duration: str = discord.Option(description="Timer duration (e.g. 5m, 10s, 1h30m)"),
            label: str = discord.Option(description="Label or event name (e.g. mafia, scrims)"),
        ):
            try:
                await self.create_timer(ctx.channel, ctx.author, time_duration, label)
                await ctx.respond("✨ Countdown timer created.", ephemeral=True)
            except ValueError as ve:
                await ctx.respond(f"❌ {ve}", ephemeral=True)
            except Exception as e:
                await ctx.respond(f"❌ Failed creating timer: {e}", ephemeral=True)

    else:
        @app_commands.command(name="timer", description="Set an aesthetic countdown timer for games or events.")
        async def timer_app(
            self,
            interaction: discord.Interaction,
            time_duration: str,
            label: str,
        ):
            try:
                await self.create_timer(interaction.channel, interaction.user, time_duration, label)
                await interaction.response.send_message("✨ Countdown timer created.", ephemeral=True)
            except ValueError as ve:
                await interaction.response.send_message(f"❌ {ve}", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"❌ Failed creating timer: {e}", ephemeral=True)

    @commands.command(name="timer")
    async def timer_prefix(self, ctx: commands.Context, time_duration: Optional[str] = None, *, label: Optional[str] = None):
        """Prefix command fallback (!timer <time> <label> / nym timer 5m mafia)."""
        if not time_duration or not label:
            return await ctx.send("⚠️ Usage: `!timer <duration> <label>` (e.g. `!timer 5m mafia`).")

        try:
            await self.create_timer(ctx.channel, ctx.author, time_duration, label)
            try:
                await ctx.message.delete()
            except Exception: pass
        except ValueError as ve:
            await ctx.send(f"❌ {ve}")
        except Exception as e:
            await ctx.send(f"❌ Failed creating timer: {e}")


if IS_PYCORD:
    def setup(bot: commands.Bot):
        bot.add_cog(TimerCog(bot))
else:
    async def setup(bot: commands.Bot):
        await bot.add_cog(TimerCog(bot))
