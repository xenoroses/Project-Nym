import os
import json
import logging
from typing import List
import discord
from discord.ext import commands
from src.config.settings import Settings
from src.database.db import DatabaseManager
from src.utils.upstash import UpstashRedis
from src.utils.health_server import HealthServer

logger = logging.getLogger("Nym")

DEFAULT_PREFIXES: List[str] = ["nym ", "nym", "!", ","]


async def get_prefix(bot, message: discord.Message):
    """Dynamic prefix resolver checking Upstash Redis cache and SQLite DB per guild."""
    if not message.guild:
        return commands.when_mentioned_or(*DEFAULT_PREFIXES)(bot, message)

    guild_id = message.guild.id
    cache_key = f"nym:prefixes:{guild_id}"
    prefixes = None

    # 1. Try Upstash Redis Cache
    if hasattr(bot, "upstash") and bot.upstash.is_configured:
        try:
            cached_json = await bot.upstash.get(cache_key)
            if not cached_json:
                cached_json = await bot.upstash.get(f"prefixes:{guild_id}")
            if cached_json:
                prefixes = json.loads(cached_json)
        except Exception:
            pass

    # 2. Fallback to SQLite DB
    if not prefixes and hasattr(bot, "db") and bot.db:
        try:
            row = await bot.db.fetch_one("SELECT prefix FROM guild_settings WHERE guild_id = ?", (guild_id,))
            if row and row["prefix"]:
                try:
                    prefixes = json.loads(row["prefix"])
                except Exception:
                    prefixes = [row["prefix"]]

                # Warm Upstash cache
                if hasattr(bot, "upstash") and bot.upstash.is_configured:
                    await bot.upstash.set(cache_key, json.dumps(prefixes))
        except Exception:
            pass

    if not prefixes:
        prefixes = DEFAULT_PREFIXES.copy()

    # Filter out 'hya' so Nym never responds to Hyacine commands
    if isinstance(prefixes, list):
        prefixes = [p for p in prefixes if p.strip().lower() != "hya"]

    # Expand prefixes (e.g. if 'nym' is set, also support 'nym ' with space if word)
    expanded = []
    for p in prefixes:
        expanded.append(p)
        if p.replace(" ", "").isalnum() and not p.endswith(" "):
            expanded.append(p + " ")

    # Deduplicate and sort by length descending
    unique_prefixes = sorted(list(set(expanded + DEFAULT_PREFIXES)), key=len, reverse=True)
    return commands.when_mentioned_or(*unique_prefixes)(bot, message)


class NymBot(commands.Bot):
    """Custom Py-Cord Bot subclass for Nym featuring auto-cog loading and database management."""

    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True  # Required for message content intent if enabled
        intents.members = True

        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            owner_id=settings.owner_id,
            debug_guilds=[settings.guild_id] if settings.guild_id else None,
            case_insensitive=True,
            help_command=None,
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
