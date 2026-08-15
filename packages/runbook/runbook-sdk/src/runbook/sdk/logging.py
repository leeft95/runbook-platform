"""Small Loguru configuration shared by the command-line entrypoints."""

from __future__ import annotations

import os
import sys

from loguru import logger

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}


def resolve_log_level(explicit: str | None = None) -> str:
    """Resolve a supported level from a flag, environment, or INFO default."""
    value = explicit or os.environ.get("RUNBOOK_LOG_LEVEL", "INFO")
    level = str(value).upper()
    if level not in _LEVELS:
        raise ValueError(f"invalid log level {value!r}; choose DEBUG, INFO, WARNING, or ERROR")
    return level


def configure_logging(level: str | None = None) -> str:
    """Configure human-readable stderr logging and return the selected level."""
    resolved = resolve_log_level(level)
    logger.remove()
    logger.add(
        sys.stderr,
        level=resolved,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
    )
    return resolved


__all__ = ["configure_logging", "resolve_log_level"]
