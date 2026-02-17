"""Security utilities for log sanitization and credential masking."""

from __future__ import annotations

import re
import shlex

from branchnexus.ui.runtime.constants import (
    AUTH_BEARER_PATTERN,
    DEFAULT_LOG_TRUNCATE_LIMIT,
    GH_TOKEN_PATTERN,
    TERMINAL_LOG_TRUNCATE_LIMIT,
    URL_CREDENTIAL_PATTERN,
)

_LEGACY_GH_TOKEN_PATTERN = re.compile(r"\bgh[pousr]_[A-Za-z0-9_]+\b")


def truncate_log(value: str, limit: int = DEFAULT_LOG_TRUNCATE_LIMIT) -> str:
    """Truncate log text to the specified limit with ellipsis."""
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def sanitize_log_text(value: str, limit: int = DEFAULT_LOG_TRUNCATE_LIMIT) -> str:
    """Mask sensitive values and return a bounded-length log string."""
    if not value:
        return ""

    sanitized = AUTH_BEARER_PATTERN.sub(r"\1 ***", value)
    sanitized = URL_CREDENTIAL_PATTERN.sub(r"\1***:***@", sanitized)
    sanitized = GH_TOKEN_PATTERN.sub("***", sanitized)
    sanitized = _LEGACY_GH_TOKEN_PATTERN.sub("***", sanitized)
    return truncate_log(sanitized, limit)


def sanitize_terminal_log_text(value: str) -> str:
    """Sanitize terminal output using stricter terminal-size truncation."""
    return sanitize_log_text(value, limit=TERMINAL_LOG_TRUNCATE_LIMIT)


def command_for_log(args: list[str]) -> str:
    """Return a shell-safe command string bounded for logging."""
    if not args:
        return ""
    return truncate_log(" ".join(shlex.quote(part) for part in args))
