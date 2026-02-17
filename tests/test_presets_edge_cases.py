"""Presets module edge case tests."""

from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.presets import (
    apply_preset,
    delete_preset,
    load_presets,
    rename_preset,
    save_preset,
)


def test_rename_preset_overwrites_existing(tmp_path) -> None:
    path = tmp_path / "config.toml"
    save_preset("a", layout="horizontal", panes=2, cleanup="session", path=path)
    save_preset("b", layout="vertical", panes=4, cleanup="persistent", path=path)
    rename_preset("a", "b", path=path)
    presets = load_presets(path)
    assert presets["b"]["layout"] == "horizontal"
    assert presets["b"]["panes"] == 2


def test_delete_nonexistent_preset_no_error(tmp_path) -> None:
    path = tmp_path / "config.toml"
    save_preset("existing", layout="grid", panes=4, cleanup="session", path=path)
    delete_preset("nonexistent", path=path)
    presets = load_presets(path)
    assert "existing" in presets


def test_apply_nonexistent_preset_raises_error(tmp_path) -> None:
    path = tmp_path / "config.toml"
    with pytest.raises(BranchNexusError) as exc_info:
        apply_preset("nonexistent", path=path)
    assert exc_info.value.code == 7  # VALIDATION_ERROR
