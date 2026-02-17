"""Retry module edge case tests."""

from __future__ import annotations

from branchnexus.retry import RecoverableError, RetryPolicy, run_with_retry


def test_retry_zero_initial_backoff_succeeds() -> None:
    call_count = {"count": 0}

    def operation():
        call_count["count"] += 1
        if call_count["count"] < 3:
            raise RecoverableError("temp")
        return "ok"

    result = run_with_retry(
        operation,
        policy=RetryPolicy(initial_backoff_seconds=0.0),
        sleep=lambda _: None,
    )
    assert result == "ok"
    assert call_count["count"] == 3


def test_retry_zero_multiplier_uses_constant_backoff() -> None:
    call_count = {"count": 0}

    def operation():
        call_count["count"] += 1
        if call_count["count"] < 3:
            raise RecoverableError("temp")
        return "ok"

    result = run_with_retry(
        operation,
        policy=RetryPolicy(initial_backoff_seconds=1.0, multiplier=0.0),
        sleep=lambda _: None,
    )
    assert result == "ok"
    assert call_count["count"] == 3


def test_retry_succeeds_first_try() -> None:
    result = run_with_retry(
        lambda: "success",
        policy=RetryPolicy(max_attempts=3),
        sleep=lambda _: None,
    )
    assert result == "success"
