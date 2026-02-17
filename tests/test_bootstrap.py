from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_module_help_output() -> None:
    process = subprocess.run(
        [sys.executable, "-m", "branchnexus", "--help"],
        cwd=ROOT,
        env={"PYTHONPATH": str(ROOT / "src")},
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode == 0
    assert "--root" in process.stdout
    assert "--layout" in process.stdout
    assert "--panes" in process.stdout
    assert "--cleanup" in process.stdout
    assert "--fresh" in process.stdout
