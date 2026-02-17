"""Repo selection screen models."""

from __future__ import annotations

from dataclasses import dataclass, field

from branchnexus.errors import BranchNexusError, ExitCode


@dataclass
class RepoSelectScreen:
    repositories: list[str]
    selected_repo: str = ""

    def select_repo(self, repo: str) -> None:
        if repo not in self.repositories:
            raise BranchNexusError(
                f"Repository is not available: {repo}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Choose one of the discovered repositories.",
            )
        self.selected_repo = repo


@dataclass
class PanelAssignmentModel:
    panes: int
    assignments: dict[int, tuple[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.panes < 2 or self.panes > 6:
            raise BranchNexusError(
                f"Invalid pane count: {self.panes}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Use pane count between 2 and 6.",
            )

    def set_assignment(self, pane: int, repo: str, branch: str) -> None:
        if pane < 1 or pane > self.panes:
            raise BranchNexusError(
                f"Pane index out of range: {pane}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Use pane indexes between 1 and selected pane count.",
            )
        if not repo or not branch:
            raise BranchNexusError(
                "Both repo and branch must be selected.",
                code=ExitCode.VALIDATION_ERROR,
                hint="Fill repo+branch selection for every pane.",
            )
        self.assignments[pane] = (repo, branch)

    def is_complete(self) -> bool:
        return len(self.assignments) == self.panes and all(self.assignments.values())
