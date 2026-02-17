"""Retry/backoff helpers for recoverable operations."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class RecoverableError(Exception):
    """Transient failure that can be retried."""


class FatalError(Exception):
    """Non-recoverable failure that should stop immediately."""


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff_seconds: float = 0.5
    multiplier: float = 2.0


def run_with_retry(
    operation: Callable[[], T],
    *,
    policy: RetryPolicy,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    attempt = 0
    backoff = policy.initial_backoff_seconds
    last_error: Exception | None = None

    while attempt < policy.max_attempts:
        attempt += 1
        try:
            return operation()
        except FatalError:
            raise
        except RecoverableError as exc:
            last_error = exc
            if attempt >= policy.max_attempts:
                break
            sleep(backoff)
            backoff *= policy.multiplier

    if last_error is not None:
        raise last_error
    raise RuntimeError("Retry policy exhausted without executing operation.")
