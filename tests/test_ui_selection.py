from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.ui.screens.branch_select import BranchSelectScreen
from branchnexus.ui.screens.repo_select import PanelAssignmentModel, RepoSelectScreen


class _BranchResult:
    def __init__(self, branches: list[str]) -> None:
        self.branches = branches


def test_repo_selection_accepts_discovered_repo_only() -> None:
    screen = RepoSelectScreen(repositories=["/a", "/b"])
    screen.select_repo("/a")
    assert screen.selected_repo == "/a"
    with pytest.raises(BranchNexusError):
        screen.select_repo("/x")


def test_branch_selection_uses_local_provider() -> None:
    screen = BranchSelectScreen(branch_provider=lambda repo: _BranchResult(["main", "feature"]))
    screen.select("/repo", "feature")
    assert screen.selected_branch == "feature"
    with pytest.raises(BranchNexusError):
        screen.select("/repo", "origin/feature")


def test_panel_assignment_requires_complete_valid_mapping() -> None:
    model = PanelAssignmentModel(panes=2)
    model.set_assignment(1, "/a", "main")
    assert model.is_complete() is False
    model.set_assignment(2, "/b", "feature")
    assert model.is_complete() is True
    with pytest.raises(BranchNexusError):
        model.set_assignment(3, "/c", "main")
