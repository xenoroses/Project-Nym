import logging
import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")


class ErrorHandlerCog(commands.Cog):
    """Global Application Command and Event Error Handler for Project Nym."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_application_command_error(
        self, ctx: discord.ApplicationContext, error: discord.DiscordException
    ):
        """Global error listener for application / slash commands."""
        # Unwrap CommandInvokeError
        original = getattr(error, "original", error)

        if isinstance(error, commands.MissingPermissions) or isinstance(original, commands.MissingPermissions):
            embed = EmbedBuilder.error(
                "Access Denied",
                "You do not have the required server permissions to execute this command.",
            )
            return await ctx.respond(embed=embed, ephemeral=True)

        if isinstance(error, commands.BotMissingPermissions) or isinstance(original, commands.BotMissingPermissions):
            embed = EmbedBuilder.error(
                "Bot Missing Permissions",
                "Nym is missing required server permissions to execute this action.",
            )
            return await ctx.respond(embed=embed, ephemeral=True)

        logger.error(f"Application command error in command '{ctx.command}': {error}", exc_info=original)

        # Build clean error response
        error_msg = str(original) if str(original) else "An unexpected error occurred."
        embed = EmbedBuilder.error(
            "Command Execution Error",
            f"❌ **{error_msg}**",
        )

        try:
            if ctx.interaction.response.is_done():
                await ctx.followup.send(embed=embed, ephemeral=True)
            else:
                await ctx.respond(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Failed sending application error response: {e}")


def setup(bot: commands.Bot):
    bot.add_cog(ErrorHandlerCog(bot))
