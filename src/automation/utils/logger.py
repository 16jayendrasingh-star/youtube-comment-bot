"""
Logger utility for YouTube Auto Video Comment Bot.

Provides consistent logging across all modules with both
file and console output.
"""

import logging
import os
from datetime import datetime


def setup_logger(log_file: str = "logs/activity.log", log_level: str = "INFO") -> logging.Logger:
    """
    Set up and return a configured logger instance.

    Args:
        log_file: Path to the log file.
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        Configured logging.Logger instance.
    """
    # Create logs directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # Create logger
    logger = logging.getLogger("youtube_comment_bot")
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console_format = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_format)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info("Logger initialized. Log file: %s", os.path.abspath(log_file))
    return logger
