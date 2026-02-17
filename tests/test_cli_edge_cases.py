"""CLI module edge case tests."""

from __future__ import annotations

from branchnexus import cli


def test_cli_invalid_log_level_returns_error() -> None:
    code = cli.main(["--log-level", "INVALID"])
    assert code == 2


def test_cli_invalid_layout_returns_error() -> None:
    code = cli.main(["--layout", "invalid"])
    assert code == 2


def test_cli_invalid_cleanup_returns_error() -> None:
    code = cli.main(["--cleanup", "invalid"])
    assert code == 2


def test_cli_panes_at_min_boundary() -> None:
    code = cli.main(["--panes", "2"])
    assert code == 0


def test_cli_panes_at_max_boundary() -> None:
    code = cli.main(["--panes", "6"])
    assert code == 0


def test_cli_panes_below_min_returns_error() -> None:
    code = cli.main(["--panes", "1"])
    assert code == 2


def test_cli_panes_above_max_returns_error() -> None:
    code = cli.main(["--panes", "7"])
    assert code == 2
