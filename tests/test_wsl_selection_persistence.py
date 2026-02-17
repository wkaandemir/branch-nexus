from __future__ import annotations

from pathlib import Path

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.runtime.wsl_selection import (
    persist_distribution,
    preload_distribution,
    require_distribution,
)


def test_distribution_persist_and_restore(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    persist_distribution("Ubuntu", config_path)
    selected = preload_distribution(["Ubuntu", "Debian"], config_path)
    assert selected == "Ubuntu"


def test_missing_saved_distribution_forces_reselection(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    persist_distribution("Legacy", config_path)
    selected = preload_distribution(["Ubuntu", "Debian"], config_path)
    assert selected == ""


def test_require_distribution_raises_when_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    with pytest.raises(BranchNexusError):
        require_distribution(["Ubuntu"], config_path)
