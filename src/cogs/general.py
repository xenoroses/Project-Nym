import time
import discord
from discord.ext import commands
from src.utils.embeds import EmbedBuilder
from src.views.confirm_view import ConfirmView


class General(commands.Cog):
    """General utility commands for Nym with Nekotina styling."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Ping Commands ---

    @discord.slash_command(name="ping", description="Check the bot's latency and response time.")
    async def ping_slash(self, ctx: discord.ApplicationContext):
        """Slash command to verify bot responsiveness."""
        ws_latency = round(self.bot.latency * 1000, 2)
        start_time = time.perf_counter()

        embed = EmbedBuilder.info(
            title="Pong! 🏓",
            description=f"**Websocket Latency:** `{ws_latency} ms`",
            author=ctx.author,
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

    @commands.command(name="ping")
    async def ping_prefix(self, ctx: commands.Context):
        """Prefix command fallback (nym ping / !ping)."""
        ws_latency = round(self.bot.latency * 1000, 2)
        start_time = time.perf_counter()

        embed = EmbedBuilder.info(
            title="Pong! 🏓",
            description=f"**Websocket Latency:** `{ws_latency} ms`",
            author=ctx.author,
        )
        view = ConfirmView(author_id=ctx.author.id)

        msg = await ctx.send(embed=embed, view=view)
        end_time = time.perf_counter()

        rtt_latency = round((end_time - start_time) * 1000, 2)
        embed.description = (
            f"**Websocket Latency:** `{ws_latency} ms`\n"
            f"**API Response Time:** `{rtt_latency} ms`"
        )
        await msg.edit(embed=embed, view=view)

    # --- Info Commands ---

    @discord.slash_command(name="info", description="Display information about Nym.")
    async def info_slash(self, ctx: discord.ApplicationContext):
        """Slash command displaying information about Nym."""
        bot_user = self.bot.user
        bot_avatar = bot_user.display_avatar.url if bot_user else None

        embed = EmbedBuilder.base(
            title="✨ Nym System Architecture",
            description="Nym is a modern, modular Discord bot built with Python, Py-Cord, and SQLite.",
            color=EmbedBuilder.COLOR_NEKOTINA,
            author=ctx.author,
            thumbnail_url=bot_avatar,
        )
        embed.add_field(name="Framework", value="Py-Cord 2.8+", inline=True)
        embed.add_field(name="Architecture", value="Async Cogs", inline=True)
        embed.add_field(name="Database", value="SQLite (aiosqlite)", inline=True)
        embed.add_field(name="Cache Layer", value="Upstash Redis REST", inline=True)
        embed.add_field(name="Deployment", value="Render Cloud (24/7)", inline=True)

        await ctx.respond(embed=embed)

    @commands.command(name="info")
    async def info_prefix(self, ctx: commands.Context):
        """Prefix command fallback (nym info / !info)."""
        bot_user = self.bot.user
        bot_avatar = bot_user.display_avatar.url if bot_user else None

        embed = EmbedBuilder.base(
            title="✨ Nym System Architecture",
            description="Nym is a modern, modular Discord bot built with Python, Py-Cord, and SQLite.",
            color=EmbedBuilder.COLOR_NEKOTINA,
            author=ctx.author,
            thumbnail_url=bot_avatar,
        )
        embed.add_field(name="Framework", value="Py-Cord 2.8+", inline=True)
        embed.add_field(name="Architecture", value="Async Cogs", inline=True)
        embed.add_field(name="Database", value="SQLite (aiosqlite)", inline=True)
        embed.add_field(name="Cache Layer", value="Upstash Redis REST", inline=True)
        embed.add_field(name="Deployment", value="Render Cloud (24/7)", inline=True)

        await ctx.send(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(General(bot))
