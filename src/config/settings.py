import os
from dataclasses import dataclass
from typing import Optional
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Application configuration loaded from environment variables."""

    discord_token: str
    owner_id: Optional[int]
    guild_id: Optional[int]
    db_path: str
    log_level: str

    @classmethod
    def load(cls) -> "Settings":
        """Load and validate environment settings.

        Raises:
            ValueError: If DISCORD_TOKEN is missing or blank.
        """
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise ValueError(
                "❌ DISCORD_TOKEN is missing in .env!\n"
                "Please open .env and set your bot token (e.g. DISCORD_TOKEN=your_token_here)."
            )

        owner_id_raw = os.getenv("OWNER_ID", "").strip()
        guild_id_raw = os.getenv("GUILD_ID", "").strip()

        owner_id = int(owner_id_raw) if owner_id_raw.isdigit() else None
        guild_id = int(guild_id_raw) if guild_id_raw.isdigit() else None
        db_path = os.getenv("DB_PATH", "nym.db").strip()
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

        return cls(
            discord_token=token,
            owner_id=owner_id,
            guild_id=guild_id,
            db_path=db_path,
            log_level=log_level,
        )
