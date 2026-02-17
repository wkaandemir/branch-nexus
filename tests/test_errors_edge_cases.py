"""Errors module edge case tests."""

from __future__ import annotations

from branchnexus.errors import BranchNexusError, ExitCode, user_facing_error


def test_user_facing_error_without_hint() -> None:
    result = user_facing_error("something went wrong")
    assert result == "Error: something went wrong."


def test_user_facing_error_with_hint() -> None:
    result = user_facing_error("something went wrong", hint="try again")
    assert result == "Error: something went wrong. Next step: try again"


def test_exit_code_values() -> None:
    assert int(ExitCode.SUCCESS) == 0
    assert int(ExitCode.INVALID_ARGS) == 2
    assert int(ExitCode.CONFIG_ERROR) == 3
    assert int(ExitCode.RUNTIME_ERROR) == 4
    assert int(ExitCode.GIT_ERROR) == 5
    assert int(ExitCode.TMUX_ERROR) == 6
    assert int(ExitCode.VALIDATION_ERROR) == 7
    assert int(ExitCode.UNSUPPORTED_PLATFORM) == 8


def test_branch_nexus_error_str_with_hint() -> None:
    error = BranchNexusError("msg", hint="hint")
    assert "hint" in str(error)


def test_branch_nexus_error_str_without_hint() -> None:
    error = BranchNexusError("msg")
    assert str(error) == "msg"
