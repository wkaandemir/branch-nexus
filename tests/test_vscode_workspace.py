from __future__ import annotations

import json
from pathlib import Path

from branchnexus.workspace.vscode import build_workspace_model, write_workspace_file


def test_workspace_model_contains_all_worktrees() -> None:
    model = build_workspace_model(["/wt/main", "/wt/feature"], name="BNX")
    assert model["name"] == "BNX"
    assert [folder["path"] for folder in model["folders"]] == ["/wt/main", "/wt/feature"]


def test_workspace_file_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "bnx.code-workspace"
    path = write_workspace_file(output, ["/wt/main", "/wt/feature"], name="BNX")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload == {
        "name": "BNX",
        "folders": [{"path": "/wt/main"}, {"path": "/wt/feature"}],
        "settings": {"files.exclude": {"**/.git": True}},
    }
