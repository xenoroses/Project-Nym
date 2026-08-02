import time
import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder
from src.views.confirm_view import ConfirmView


class General(commands.Cog):
    """General utility commands for Nym."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @discord.slash_command(name="ping", description="Check the bot's latency and response time.")
    async def ping(self, ctx: discord.ApplicationContext):
        """Slash command to verify bot responsiveness."""
        ws_latency = round(self.bot.latency * 1000, 2)
        start_time = time.perf_counter()

        embed = EmbedBuilder.info(
            title="🏓 Pong!",
            description=f"**Websocket Latency:** `{ws_latency} ms`",
            footer="Nym Bot • Status Operational",
        )
        view = ConfirmView(author_id=ctx.author.id)

        await ctx.respond(embed=embed, view=view)
        end_time = time.perf_counter()

        rtt_latency = round((end_time - start_time) * 1000, 2)
        embed.description = (
            f"**Websocket Latency:** `{ws_latency} ms`\n"
            f"**API Response Time:** `{rtt_latency} ms`"
        )
        await ctx.interaction.edit_original_response(embed=embed, view=view)


    @discord.slash_command(name="info", description="Display information about Nym.")
    async def info(self, ctx: discord.ApplicationContext):
        """Displays information about Nym bot."""
        embed = EmbedBuilder.info(
            title="🤖 Nym Bot",
            description="Nym is a modular Discord bot built with Python & Py-Cord.",
            footer=f"Serving {len(self.bot.guilds)} guilds",
        )
        embed.add_field(name="Framework", value="Py-Cord", inline=True)
        embed.add_field(name="Architecture", value="Modular Cogs", inline=True)
        embed.add_field(name="Database", value="SQLite (aiosqlite)", inline=True)

        await ctx.respond(embed=embed)


def setup(bot: commands.Bot):
    """Cog setup function loaded by Py-Cord."""
    bot.add_cog(General(bot))
