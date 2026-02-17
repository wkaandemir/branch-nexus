"""WSL selection models."""

from __future__ import annotations

from dataclasses import dataclass

from branchnexus.errors import BranchNexusError, ExitCode


@dataclass
class WslSelectScreen:
    distributions: list[str]
    selected: str = ""

    def select(self, distribution: str) -> None:
        if distribution not in set(self.distributions):
            raise BranchNexusError(
                f"Unsupported WSL distribution: {distribution}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Select one of the discovered distributions.",
            )
        self.selected = distribution

    def can_continue(self) -> bool:
        return bool(self.selected)
