import os
import logging
import discord
from discord.ext import commands
from src.config.settings import Settings
from src.database.db import DatabaseManager
from src.utils.upstash import UpstashRedis
from src.utils.health_server import HealthServer

logger = logging.getLogger("Nym")


class NymBot(commands.Bot):
    """Custom Py-Cord Bot subclass for Nym featuring auto-cog loading and database management."""

    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True  # Required for message content intent if enabled
        intents.members = True

        super().__init__(
            intents=intents,
            owner_id=settings.owner_id,
            debug_guilds=[settings.guild_id] if settings.guild_id else None,
        )

        self.settings = settings
        self.db = DatabaseManager(db_path=settings.db_path)
        self.upstash = UpstashRedis(
            rest_url=settings.upstash_redis_rest_url,
            rest_token=settings.upstash_redis_rest_token,
        )
        self.health_server = HealthServer()

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        """Connect to database, start HTTP health server, load cogs and events, then start bot execution."""
        # 1. Connect to SQLite database
        await self.db.connect()

        # 2. Start HTTP health check server for Render & uptime monitoring
        await self.health_server.start()

        # 3. Auto-load all cogs from src/cogs/
        self._load_extensions_from_dir("src/cogs", "src.cogs")

        # 4. Auto-load all event listeners from src/events/
        self._load_extensions_from_dir("src/events", "src.events")

        # 5. Start Discord bot client
        logger.info("Starting Nym Discord client...")
        await super().start(token, reconnect=reconnect)

    async def close(self) -> None:
        """Gracefully shut down database connections, health server, and bot client."""
        logger.info("Shutting down Nym Bot...")
        await self.health_server.stop()
        await self.upstash.close()
        await self.db.close()
        await super().close()


    def _load_extensions_from_dir(self, dir_path: str, module_prefix: str) -> None:
        """Scan directory and dynamically load extension modules."""
        if not os.path.exists(dir_path):
            logger.warning(f"Directory '{dir_path}' does not exist, skipping extension loading.")
            return

        loaded_count = 0
        for filename in os.listdir(dir_path):
            if filename.endswith(".py") and not filename.startswith("__"):
                module_name = f"{module_prefix}.{filename[:-3]}"
                try:
                    self.load_extension(module_name)
                    logger.info(f"Loaded extension: {module_name}")
                    loaded_count += 1
                except Exception as e:
                    logger.error(f"Failed to load extension {module_name}: {e}", exc_info=True)

        logger.info(f"Successfully loaded {loaded_count} extension(s) from '{dir_path}'.")
