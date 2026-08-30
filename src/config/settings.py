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
    openrouter_key: Optional[str]
    upstash_redis_rest_url: Optional[str]
    upstash_redis_rest_token: Optional[str]

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

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        data_dir = os.path.join(base_dir, "data")
        os.makedirs(data_dir, exist_ok=True)
        default_db = os.path.join(data_dir, "nym.db")

        db_path = os.getenv("DB_PATH", default_db).strip()
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

        openrouter_key = os.getenv("OPENROUTER_KEY", "").strip() or None
        upstash_redis_rest_url = (os.getenv("UPSTASH_REDIS_REST_URL", "").strip().strip('"') or "https://great-camel-72413.upstash.io")
        upstash_redis_rest_token = (os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip().strip('"') or "gQAAAAAAARrdAAIgcDJhNGMyOWYzMmY5MjQ0YmYxYjI2NWI1N2NhZWNiNmZjZQ")

        return cls(
            discord_token=token,
            owner_id=owner_id,
            guild_id=guild_id,
            db_path=db_path,
            log_level=log_level,
            openrouter_key=openrouter_key,
            upstash_redis_rest_url=upstash_redis_rest_url,
            upstash_redis_rest_token=upstash_redis_rest_token,
        )

