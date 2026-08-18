"""Structured logging configuration for DailyAI pipeline."""

import logging
import os
import sys
from typing import Optional
from rich.console import Console
from rich.logging import RichHandler

_configured = False


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    rich_console: bool = True,
) -> logging.Logger:
    """Configure structured logging for the application.

    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_file: Optional path to a file where logs should be appended.
        rich_console: Whether to use Rich colorful console handler.

    Returns:
        Root logger configured for DailyAI.
    """
    global _configured
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    root_logger = logging.getLogger()
    # Remove existing handlers to avoid duplicates on re-configuration
    if root_logger.handlers:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)

    root_logger.setLevel(numeric_level)

    handlers = []

    if rich_console:
        console_handler = RichHandler(
            console=Console(file=sys.stderr),
            show_time=True,
            show_path=False,
            rich_tracebacks=True,
            tracebacks_show_locals=False,
            markup=True,
        )
        console_handler.setLevel(numeric_level)
        handlers.append(console_handler)
    else:
        stream_handler = logging.StreamHandler(sys.stderr)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)8s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(numeric_level)
        handlers.append(stream_handler)

    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_formatter = logging.Formatter(
            fmt='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}',
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(numeric_level)
        handlers.append(file_handler)

    for h in handlers:
        root_logger.addHandler(h)

    # Silence noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)

    _configured = True
    return logging.getLogger("dailyai")


def get_logger(name: str) -> logging.Logger:
    """Get a named logger within the dailyai namespace."""
    if not _configured:
        setup_logging()
    if name.startswith("dailyai"):
        return logging.getLogger(name)
    return logging.getLogger(f"dailyai.{name}")
