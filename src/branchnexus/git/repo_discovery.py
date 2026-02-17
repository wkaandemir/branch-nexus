"""Recursive git repository discovery."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_IGNORES = {".venv", "node_modules", "__pycache__", ".pytest_cache"}


def discover_repositories(root: str | Path, ignore_dirs: set[str] | None = None) -> list[Path]:
    start = Path(root).expanduser().resolve()
    if not start.exists() or not start.is_dir():
        return []

    ignored = DEFAULT_IGNORES | (ignore_dirs or set())
    seen: set[Path] = set()
    repos: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(start, topdown=True):
        current = Path(dirpath)
        dirnames[:] = [
            name
            for name in dirnames
            if name not in ignored
        ]

        if ".git" in dirnames or ".git" in filenames:
            resolved = current.resolve()
            if resolved not in seen:
                seen.add(resolved)
                repos.append(resolved)
            dirnames[:] = []

    repos.sort(key=lambda item: str(item).lower())
    return repos
