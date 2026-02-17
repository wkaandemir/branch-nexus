"""Local branch selection models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from branchnexus.errors import BranchNexusError, ExitCode


@dataclass
class BranchSelectScreen:
    branch_provider: Callable[[str], object]
    selected_repo: str = ""
    selected_branch: str = ""

    def list_branches(self, repo: str) -> list[str]:
        result = self.branch_provider(repo)
        branches = result.branches if hasattr(result, "branches") else list(result)
        return sorted(branches)

    def select(self, repo: str, branch: str) -> None:
        branches = self.list_branches(repo)
        if branch not in branches:
            raise BranchNexusError(
                f"Local branch not found: {branch}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Select a branch from local branch list.",
            )
        self.selected_repo = repo
        self.selected_branch = branch
