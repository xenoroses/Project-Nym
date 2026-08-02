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
                last_message_id INTEGER,
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
