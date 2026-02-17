from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.ui.screens.layout_config import LayoutConfigScreen
from branchnexus.ui.screens.wsl_select import WslSelectScreen


def test_layout_and_cleanup_validation() -> None:
    screen = LayoutConfigScreen()
    screen.set_layout("horizontal")
    screen.set_panes(6)
    screen.set_cleanup_policy("persistent")
    assert screen.layout == "horizontal"
    assert screen.panes == 6
    assert screen.cleanup_policy == "persistent"

    with pytest.raises(BranchNexusError):
        screen.set_panes(7)


def test_wsl_selection_is_required() -> None:
    wsl = WslSelectScreen(distributions=["Ubuntu", "Debian"])
    assert wsl.can_continue() is False
    wsl.select("Ubuntu")
    assert wsl.can_continue() is True

    with pytest.raises(BranchNexusError):
        wsl.select("Arch")
