from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _env_with_pythonpath() -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    src_path = str(Path("src").resolve())
    env["PYTHONPATH"] = f"{src_path}{os.pathsep}{existing}" if existing else src_path
    return env


def test_cli_module_reports_invalid_args_via_exit_code(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "branchnexus", "--panes", "7", "--log-file", str(tmp_path / "bnx.log")],
        capture_output=True,
        text=True,
        check=False,
        env=_env_with_pythonpath(),
    )

    assert completed.returncode == 2
    assert "--panes must be between 2 and 6" in completed.stderr


def test_cli_module_runs_non_gui_flow_with_valid_flags(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "branchnexus",
            "--terminal-template",
            "4",
            "--max-terminals",
            "16",
            "--log-level",
            "warning",
            "--log-file",
            str(tmp_path / "bnx.log"),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_env_with_pythonpath(),
    )

    assert completed.returncode == 0
