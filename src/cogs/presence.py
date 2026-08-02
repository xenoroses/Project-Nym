import logging
import itertools
import discord
from discord.ext import commands, tasks

logger = logging.getLogger("Nym")


class PresenceCog(commands.Cog):
    """Aesthetic Presence & Activity Rotator for Project Nym."""

    PRESENCE_POOL = [
        {
            "status": discord.Status.idle,
            "activity": discord.Activity(
                type=discord.ActivityType.watching,
                name="over Zen's domain 🌸 | Destined to be Zen's~"
            )
        },
        {
            "status": discord.Status.dnd,
            "activity": discord.Activity(
                type=discord.ActivityType.watching,
                name="Zen's starry realm ✨ | Bound to Zen's soul"
            )
        },
        {
            "status": discord.Status.online,
            "activity": discord.Activity(
                type=discord.ActivityType.watching,
                name="Zen's subtle whispers 💫 | Forever Zen's~"
            )
        },
        {
            "status": discord.Status.idle,
            "activity": discord.Activity(
                type=discord.ActivityType.watching,
                name="Zen's peaceful sanctuary 🌙 | Destined to be Zen's~"
            )
        },
    ]

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.presence_cycle = itertools.cycle(self.PRESENCE_POOL)
        self.rotate_presence.start()

    def cog_unload(self):
        self.rotate_presence.cancel()

    @tasks.loop(minutes=3)
    async def rotate_presence(self):
        """Rotate Nym's status and watching activity periodically."""
        try:
            entry = next(self.presence_cycle)
            await self.bot.change_presence(
                status=entry["status"],
                activity=entry["activity"]
            )
            logger.info(f"✨ Updated presence activity: Watching {entry['activity'].name}")
        except Exception as e:
            logger.warning(f"Failed to update presence activity: {e}")

    @rotate_presence.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()


def setup(bot: commands.Bot):
    bot.add_cog(PresenceCog(bot))
