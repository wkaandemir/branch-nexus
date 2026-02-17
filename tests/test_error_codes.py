from __future__ import annotations

from branchnexus.errors import BranchNexusError, ExitCode, user_facing_error
from branchnexus.logging import LOG_LEVELS, configure_logging


def test_exit_codes_are_deterministic() -> None:
    assert int(ExitCode.SUCCESS) == 0
    assert int(ExitCode.INVALID_ARGS) == 2
    assert int(ExitCode.UNSUPPORTED_PLATFORM) == 8


def test_branch_nexus_error_string_contains_hint() -> None:
    err = BranchNexusError("tmux not found", code=ExitCode.TMUX_ERROR, hint="Install tmux")
    assert "Install tmux" in str(err)


def test_user_facing_error_template() -> None:
    text = user_facing_error("Invalid pane count", hint="Use 2-6")
    assert text.startswith("Error:")
    assert "Next step" in text


def test_logging_levels() -> None:
    logger = configure_logging("WARN")
    assert logger.level == LOG_LEVELS["WARN"]
