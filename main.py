import sys
from src.config.settings import Settings
from src.utils.logger import setup_logger
from src.bot import NymBot


def main():
    """Main application entry point for Nym Bot."""
    try:
        # 1. Load and validate environment configuration
        settings = Settings.load()

        # 2. Initialize colorlog logger & log file
        logger = setup_logger(log_level=settings.log_level)
        logger.info("Initializing Project Nym...")

        # 3. Instantiate bot
        bot = NymBot(settings=settings)

        # 4. Start bot execution
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
