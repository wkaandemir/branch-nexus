from __future__ import annotations

import pytest

from branchnexus.retry import FatalError, RecoverableError, RetryPolicy, run_with_retry


def test_retry_policy_recovers_after_transient_failures() -> None:
    attempts = {"count": 0}

    def operation() -> str:
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RecoverableError("temporary")
        return "ok"

    result = run_with_retry(operation, policy=RetryPolicy(max_attempts=4), sleep=lambda _: None)
    assert result == "ok"
    assert attempts["count"] == 3


def test_retry_policy_stops_on_fatal_error() -> None:
    def operation() -> str:
        raise FatalError("fatal")

    with pytest.raises(FatalError):
        run_with_retry(operation, policy=RetryPolicy(max_attempts=5), sleep=lambda _: None)


def test_retry_policy_raises_last_recoverable_error() -> None:
    def operation() -> str:
        raise RecoverableError("temporary")

    with pytest.raises(RecoverableError):
        run_with_retry(operation, policy=RetryPolicy(max_attempts=2), sleep=lambda _: None)
