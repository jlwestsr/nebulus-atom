import logging
import os
from logging.handlers import RotatingFileHandler
from nebulus_atom.config import Config


def setup_logger(name: str) -> logging.Logger:
    """
    Configures and returns a logger with rotating file handler.
    """
    # Ensure log directory exists
    if not os.path.exists(Config.LOG_DIR):
        try:
            os.makedirs(Config.LOG_DIR)
        except OSError:
            # Fallback if we can't create the directory (e.g. permission issues)
            pass

    logger = logging.getLogger(name)

    # If logger already has handlers, assume it's configured to avoid duplicates
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    try:
        # Rotating File Handler: 5MB max, 3 backups
        file_handler = RotatingFileHandler(
            Config.LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (IOError, PermissionError):
        # If we can't write to file, create a NullHandler to suppress errors
        logger.addHandler(logging.NullHandler())

    # We do NOT add a StreamHandler (stdout) here because CLI/TUI views handle
    # user-facing output. We don't want logs polluting the UI unless explicitly requested.

    return logger
