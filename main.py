import os
import sys
import time
import asyncio
import urllib.request
from src.config.settings import Settings
from src.utils.logger import setup_logger
from src.utils.health_server import HealthServer
from src.bot import NymBot

PRIMARY_HF_URL = "https://xenoroses-project-nym.hf.space"


def is_hf_primary_active(timeout: float = 4.0) -> bool:
    """Check if primary bot hosting node on Hugging Face Spaces is online."""
    try:
        req = urllib.request.Request(PRIMARY_HF_URL, headers={"User-Agent": "Nym-Cluster/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.getcode() == 200
    except Exception:
        return False


async def run_render_standby(settings: Settings, logger):
    """Run lightweight HealthServer on Render to keep UptimeRobot alive while preventing duplicate Discord Gateway sessions."""
    logger.info("🌐 Initializing Render Health Server on port %s...", settings.port)
    server = HealthServer(port=settings.port)
    await server.start()
    logger.info("✅ Render standby monitor active. Primary Nym Bot is handling Discord on Hugging Face Spaces.")

    # Loop and monitor: if HF Spaces ever goes offline, failover to active Discord Bot
    while True:
        await asyncio.sleep(60)
        if not is_hf_primary_active():
            logger.warning("⚠️ Primary Hugging Face Space is unreachable! Engaging Render active failover bot...")
            await server.stop()
            bot = NymBot(settings=settings)
            await bot.start(settings.discord_token)
            break


def main():
    """Main application entry point for Nym Bot."""
    try:
        # 1. Load and validate environment configuration
        settings = Settings.load()

        # 2. Initialize colorlog logger & log file
        logger = setup_logger(log_level=settings.log_level)
        logger.info("Initializing Project Nym...")

        # 3. Inter-Host Coordination (Render vs Hugging Face Spaces)
        # When running on Render and Hugging Face is the active primary, run in standby mode to prevent gateway collisions
        is_render = os.getenv("RENDER") == "true" or os.getenv("IS_RENDER") == "true"
        if is_render and not os.getenv("SPACE_ID"):
            if is_hf_primary_active():
                logger.info("⚡ Primary node detected active on Hugging Face Spaces. Starting Render in Standby / Health-Check mode.")
                asyncio.run(run_render_standby(settings, logger))
                return

        # 4. Instantiate bot & start Discord Gateway
        bot = NymBot(settings=settings)
        bot.run(settings.discord_token)

    except ValueError as e:
        print(f"\nConfiguration Error: {e}\n", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nShutdown requested by user. Exiting Nym Bot gracefully.\n")
        sys.exit(0)
    except Exception as e:
        print(f"\nFatal startup error: {e}\n", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
