"""VS Code multi-root workspace generator."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path


def build_workspace_model(worktree_paths: Iterable[str], *, name: str = "BranchNexus") -> dict:
    folders = [{"path": path} for path in worktree_paths]
    return {
        "name": name,
        "folders": folders,
        "settings": {
            "files.exclude": {
                "**/.git": True,
            }
        },
    }


def write_workspace_file(
    output_path: str | Path,
    worktree_paths: Iterable[str],
    *,
    name: str = "BranchNexus",
) -> Path:
    path = Path(output_path)
    payload = build_workspace_model(worktree_paths, name=name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
