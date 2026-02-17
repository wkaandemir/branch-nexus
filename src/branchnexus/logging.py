"""Application logging helpers."""

from __future__ import annotations

import logging as py_logging
import sys
from pathlib import Path
from typing import TextIO

LOG_LEVELS = {
    "DEBUG": py_logging.DEBUG,
    "INFO": py_logging.INFO,
    "WARN": py_logging.WARNING,
    "WARNING": py_logging.WARNING,
    "ERROR": py_logging.ERROR,
}
DEFAULT_LOG_PATH = Path("~/.config/branchnexus/logs/branchnexus.log")
_FALLBACK_LOG_PATH = Path(".branchnexus/logs/branchnexus.log")
_FORMAT = "%(asctime)s %(levelname)s %(name)s:%(lineno)d %(message)s"


def default_log_path() -> Path:
    try:
        resolved = DEFAULT_LOG_PATH.expanduser()
    except RuntimeError:
        resolved = (Path.cwd() / _FALLBACK_LOG_PATH).resolve()
    else:
        if not resolved.is_absolute():
            resolved = resolved.resolve()
    return resolved


def configure_logging(
    level: str = "INFO",
    stream: TextIO | None = None,
    *,
    log_file: str | Path | None = None,
) -> py_logging.Logger:
    normalized = level.upper()
    if normalized == "WARNING":
        normalized = "WARN"
    resolved = LOG_LEVELS.get(normalized, py_logging.INFO)

    logger = py_logging.getLogger("branchnexus")
    logger.setLevel(resolved)
    logger.handlers.clear()
    formatter = py_logging.Formatter(_FORMAT)

    handler = py_logging.StreamHandler(stream or sys.stderr)
    handler.setLevel(resolved)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if log_file:
        try:
            log_path = Path(log_file).expanduser()
        except RuntimeError:
            log_path = Path(log_file)
        if not log_path.is_absolute():
            log_path = log_path.resolve()
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = py_logging.FileHandler(log_path, encoding="utf-8")
        except OSError:
            pass
        else:
            file_handler.setLevel(py_logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

    logger.propagate = False
    return logger
