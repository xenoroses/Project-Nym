import logging
import os
import sys
import colorlog

# Reconfigure stdout on Windows to support emojis and UTF-8 characters in terminal
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass



def setup_logger(log_level: str = "INFO", log_file: str = "logs/nym.log") -> logging.Logger:
    """Configures colorlog console output and file logging.

    Args:
        log_level: Logging level (e.g. DEBUG, INFO, WARNING, ERROR).
        log_file: Relative or absolute path for file output.

    Returns:
        Configured Logger instance.
    """
    # Ensure logs directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Base logger setup
    logger = logging.getLogger("Nym")
    logger.setLevel(numeric_level)
    logger.handlers.clear()

    # Console Handler (Colorlog)
    console_formatter = colorlog.ColoredFormatter(
        "%(log_color)s[%(asctime)s] [%(levelname)s] %(name)s:%(reset)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File Handler
    file_formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Reduce noise from noisy third-party libraries if necessary
    logging.getLogger("discord").setLevel(logging.WARNING)

    return logger


def get_logger() -> logging.Logger:
    """Retrieves the Nym application logger."""
    return logging.getLogger("Nym")
