import logging
from typing import Any, List, Optional, Tuple
import aiosqlite

logger = logging.getLogger("Nym")


class DatabaseManager:
    """Async SQLite Database Manager using aiosqlite."""

    def __init__(self, db_path: str = "nym.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        """Establish connection to SQLite database and initialize tables."""
        logger.info(f"Connecting to SQLite database at '{self.db_path}'...")
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._init_tables()
        logger.info("Database connection established and schema verified.")

    async def _init_tables(self) -> None:
        """Initialize database tables and initial schema."""
        if not self._db:
            raise RuntimeError("Database connection is not initialized.")

        # Example Table: Guild Settings
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT DEFAULT '!',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Table: Sticky Messages
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS sticky_messages (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                message TEXT NOT NULL,
                is_embed INTEGER DEFAULT 0,
                last_message_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        try:
            await self._db.execute("ALTER TABLE sticky_messages ADD COLUMN is_embed INTEGER DEFAULT 0")
        except Exception:
            pass


        # Table: Bot Admins
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_admins (
                user_id INTEGER PRIMARY KEY,
                added_by INTEGER,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await self._db.execute(
            "INSERT OR IGNORE INTO bot_admins (user_id, added_by) VALUES (?, ?)",
            (896740108059959316, 456811056090578975)
        )

        # Table: AutoDelete Configs
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS autodelete_configs (
                channel_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                enabled INTEGER DEFAULT 1,
                duration_seconds INTEGER DEFAULT 3600,
                filter_mode TEXT DEFAULT 'all',
                exempt_pinned INTEGER DEFAULT 1,
                exempt_bots INTEGER DEFAULT 1,
                exempt_admins INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Table: AutoDelete Queue
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS autodelete_queue (
                message_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL,
                delete_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Table: NymLock Users
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS nymlock_users (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                locked_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )

        # Table: Confession Configs
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS confession_configs (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                log_channel_id INTEGER,
                count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Table: Confessions Log
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS confessions_log (
                confession_id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        await self._db.commit()







    async def close(self) -> None:
        """Close the database connection gracefully."""
        if self._db:
            await self._db.close()
            logger.info("Database connection closed.")

    async def execute(self, query: str, params: Tuple[Any, ...] = ()) -> aiosqlite.Cursor:
        """Execute a write/update query."""
        if not self._db:
            raise RuntimeError("Database not connected.")
        cursor = await self._db.execute(query, params)
        await self._db.commit()
        return cursor

    async def fetch_one(self, query: str, params: Tuple[Any, ...] = ()) -> Optional[aiosqlite.Row]:
        """Fetch a single record matching query."""
        if not self._db:
            raise RuntimeError("Database not connected.")
        async with self._db.execute(query, params) as cursor:
            return await cursor.fetchone()

    async def fetch_all(self, query: str, params: Tuple[Any, ...] = ()) -> List[aiosqlite.Row]:
        """Fetch all records matching query."""
        if not self._db:
            raise RuntimeError("Database not connected.")
        async with self._db.execute(query, params) as cursor:
            return await cursor.fetchall()
