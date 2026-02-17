from __future__ import annotations

from pathlib import Path

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.presets import (
    TERMINAL_TEMPLATE_CATALOG,
    apply_preset,
    delete_preset,
    load_presets,
    rename_preset,
    resolve_terminal_template,
    save_preset,
    terminal_template_choices,
)


def test_preset_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_preset("daily", layout="grid", panes=4, cleanup="session", path=path)
    presets = load_presets(path)
    assert presets["daily"]["layout"] == "grid"


def test_apply_preset_returns_expected_values(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_preset("focus", layout="vertical", panes=2, cleanup="persistent", path=path)
    payload = apply_preset("focus", path)
    assert payload == {"layout": "vertical", "panes": 2, "cleanup": "persistent"}


def test_rename_and_delete_preset(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    save_preset("old", layout="grid", panes=3, cleanup="session", path=path)
    rename_preset("old", "new", path)
    assert "new" in load_presets(path)
    delete_preset("new", path)
    assert "new" not in load_presets(path)


def test_invalid_preset_validation(tmp_path: Path) -> None:
    with pytest.raises(BranchNexusError):
        save_preset("bad", layout="grid", panes=17, cleanup="session", path=tmp_path / "c.toml")


def test_terminal_template_catalog_and_custom_resolution() -> None:
    assert TERMINAL_TEMPLATE_CATALOG == (2, 4, 6, 8, 12, 16)
    assert terminal_template_choices() == ("2", "4", "6", "8", "12", "16", "custom")
    assert resolve_terminal_template("8") == 8
    assert resolve_terminal_template("custom", custom_value=15) == 15
    with pytest.raises(BranchNexusError):
        resolve_terminal_template("custom", custom_value=32)
