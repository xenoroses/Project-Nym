import os
import logging
import discord
from discord.ext import commands
from src.config.settings import Settings
from src.database.db import DatabaseManager

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

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        """Connect to database, load cogs and events, then start bot execution."""
        # 1. Connect to SQLite database
        await self.db.connect()

        # 2. Auto-load all cogs from src/cogs/
        self._load_extensions_from_dir("src/cogs", "src.cogs")

        # 3. Auto-load all event listeners from src/events/
        self._load_extensions_from_dir("src/events", "src.events")

        # 4. Start Discord bot client
        logger.info("Starting Nym Discord client...")
        await super().start(token, reconnect=reconnect)

    async def close(self) -> None:
        """Gracefully shut down database connections and bot client."""
        logger.info("Shutting down Nym Bot...")
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
