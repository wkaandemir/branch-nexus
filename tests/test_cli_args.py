from __future__ import annotations

import io
from contextlib import redirect_stderr

from branchnexus import cli
from branchnexus.errors import BranchNexusError, ExitCode


def test_cli_help_includes_public_flags() -> None:
    parser = cli.build_parser()
    help_text = parser.format_help()
    assert "--root" in help_text
    assert "--layout" in help_text
    assert "--panes" in help_text
    assert "--cleanup" in help_text
    assert "--terminal-template" in help_text
    assert "--max-terminals" in help_text
    assert "--fresh" in help_text


def test_invalid_panes_returns_error_code() -> None:
    code = cli.main(["--panes", "7"])
    assert code != 0


def test_no_args_triggers_gui_launcher() -> None:
    marker = {"called": False}

    def fake_gui() -> int:
        marker["called"] = True
        return 0

    code = cli.main([], gui_launcher=fake_gui)
    assert code == 0
    assert marker["called"]


def test_fresh_flag_triggers_gui_launcher() -> None:
    marker = {"called": False}

    def fake_gui() -> int:
        marker["called"] = True
        return 0

    code = cli.main(["--fresh"], gui_launcher=fake_gui)
    assert code == 0
    assert marker["called"]


def test_gui_error_is_reported_to_stderr() -> None:
    def fake_gui() -> int:
        raise BranchNexusError(
            "PySide6 missing",
            code=ExitCode.RUNTIME_ERROR,
            hint="Install PySide6.",
        )

    stream = io.StringIO()
    with redirect_stderr(stream):
        code = cli.main([], gui_launcher=fake_gui)

    assert code == int(ExitCode.RUNTIME_ERROR)
    assert "Install PySide6." in stream.getvalue()


def test_log_level_flag_is_accepted() -> None:
    code = cli.main(["--log-level", "DEBUG"])
    assert code == 0


def test_warning_alias_for_log_level_is_accepted() -> None:
    code = cli.main(["--log-level", "warning"])
    assert code == 0


def test_runtime_template_flags_are_accepted() -> None:
    code = cli.main(
        [
            "--terminal-template",
            "12",
            "--max-terminals",
            "16",
        ]
    )
    assert code == 0


def test_invalid_max_terminals_returns_error_code() -> None:
    code = cli.main(["--max-terminals", "32"])
    assert code != 0


def test_removed_ui_mode_flag_is_rejected() -> None:
    code = cli.main(["--ui-mode", "wizard"])
    assert code == 2


def test_template_and_max_terminals_must_be_compatible() -> None:
    code = cli.main(["--terminal-template", "12", "--max-terminals", "8"])
    assert code == int(ExitCode.VALIDATION_ERROR)
