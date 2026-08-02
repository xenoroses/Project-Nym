import datetime
import logging
import discord
from discord.ext import commands, tasks
from src.utils.embeds import EmbedBuilder

logger = logging.getLogger("Nym")


class HealthCog(commands.Cog):
    """Health check monitoring cog with 30-minute Upstash Redis ping task."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.upstash_check_loop.start()

    def cog_unload(self):
        self.upstash_check_loop.cancel()

    @tasks.loop(minutes=30)
    async def upstash_check_loop(self):
        """30-minute automated health check loop for Upstash Redis."""
        if not hasattr(self.bot, "upstash") or not self.bot.upstash.is_configured:
            logger.debug("Upstash Redis not configured, skipping 30-min heartbeat check.")
            return

        try:
            latency = await self.bot.upstash.ping()
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            await self.bot.upstash.set("nym:bot_heartbeat", now_iso, ex_seconds=3600)
            logger.info(f"💚 Upstash 30-min Health Check: PONG ({latency} ms) | Heartbeat logged at {now_iso[:19]}Z")
        except Exception as e:
            logger.warning(f"⚠️ Upstash 30-min Health Check Failed: {e}")

    @upstash_check_loop.before_loop
    async def before_upstash_loop(self):
        await self.bot.wait_until_ready()

    @discord.slash_command(name="health", description="Check Nym's operational health and database connections.")
    async def health_command(self, ctx: discord.ApplicationContext):
        """Slash command displaying comprehensive bot system health status."""
        ws_latency = round(self.bot.latency * 1000, 2)

        # Check SQLite DB
        db_status = "Connected ✅"
        try:
            row = await self.bot.db.fetch_one("SELECT 1")
            if not row:
                db_status = "Error ❌"
        except Exception as e:
            db_status = f"Error ❌ ({e})"

        # Check Upstash Redis
        upstash_status = "Not Configured ⚠️"
        upstash_latency = None
        if hasattr(self.bot, "upstash") and self.bot.upstash.is_configured:
            try:
                upstash_latency = await self.bot.upstash.ping()
                upstash_status = f"Online ({upstash_latency} ms) ✅"
            except Exception as e:
                upstash_status = f"Failed ❌ ({e})"

        embed = EmbedBuilder.info(
            title="💚 Nym System Health",
            description="Operational metrics and connectivity status.",
            footer="Nym Bot • 24/7 Keep-Alive System",
        )
        embed.add_field(name="Discord WebSocket", value=f"`{ws_latency} ms`", inline=True)
        embed.add_field(name="SQLite Database", value=f"`{db_status}`", inline=True)
        embed.add_field(name="Upstash Redis", value=f"`{upstash_status}`", inline=True)

        await ctx.respond(embed=embed)


def setup(bot: commands.Bot):
    bot.add_cog(HealthCog(bot))
