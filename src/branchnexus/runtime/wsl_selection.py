"""Persist and restore selected WSL distribution."""

from __future__ import annotations

from pathlib import Path

from branchnexus.config import AppConfig, load_config, save_config
from branchnexus.errors import BranchNexusError, ExitCode


def persist_distribution(distribution: str, path: str | Path | None = None) -> AppConfig:
    config = load_config(path)
    config.wsl_distribution = distribution
    save_config(config, path)
    return config


def preload_distribution(
    available_distributions: list[str],
    path: str | Path | None = None,
) -> str:
    config = load_config(path)
    selected = config.wsl_distribution.strip()
    if not selected:
        return ""
    if selected not in set(available_distributions):
        return ""
    return selected


def require_distribution(
    available_distributions: list[str],
    path: str | Path | None = None,
) -> str:
    selected = preload_distribution(available_distributions, path)
    if not selected:
        raise BranchNexusError(
            "A valid WSL distribution selection is required.",
            code=ExitCode.RUNTIME_ERROR,
            hint="Select one of the discovered WSL distributions.",
        )
    return selected
