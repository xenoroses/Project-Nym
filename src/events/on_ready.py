import logging
import discord
from discord.ext import commands

logger = logging.getLogger("Nym")


class OnReadyEvent(commands.Cog):
    """Event listener triggered when the bot becomes ready."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Force sync slash commands once on startup
        if not getattr(self.bot, "_commands_synced", False):
            try:
                await self.bot.sync_commands()
                self.bot._commands_synced = True
                logger.info("⚡ Application commands forced synced with Discord API.")
            except Exception as e:
                logger.warning(f"Failed syncing commands with Discord API: {e}")

        guild_count = len(self.bot.guilds)
        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        command_count = len(self.bot.commands) + len(self.bot.pending_application_commands)

        logger.info("=" * 50)
        logger.info(f"🚀 Nym Bot online as '{self.bot.user}' (ID: {self.bot.user.id})")
        logger.info(f"📊 Guild Count: {guild_count} | Total Members: {total_members}")
        logger.info(f"⚡ Synced Commands: {command_count}")
        logger.info("=" * 50)

        # Set custom status presence
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/ping | Project Nym"
            )
        )



def setup(bot: commands.Bot):
    """Event module loader."""
    bot.add_cog(OnReadyEvent(bot))
