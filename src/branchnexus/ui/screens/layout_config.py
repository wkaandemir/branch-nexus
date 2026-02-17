"""WSL/layout/session configuration models."""

from __future__ import annotations

from dataclasses import dataclass

from branchnexus.errors import BranchNexusError, ExitCode

_VALID_LAYOUTS = {"horizontal", "vertical", "grid"}
_VALID_CLEANUP = {"session", "persistent"}


@dataclass
class LayoutConfigScreen:
    layout: str = "grid"
    panes: int = 4
    cleanup_policy: str = "session"

    def set_layout(self, layout: str) -> None:
        if layout not in _VALID_LAYOUTS:
            raise BranchNexusError(
                f"Invalid layout: {layout}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Use horizontal, vertical, or grid.",
            )
        self.layout = layout

    def set_panes(self, panes: int) -> None:
        if panes < 2 or panes > 6:
            raise BranchNexusError(
                f"Invalid pane count: {panes}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Use a pane value between 2 and 6.",
            )
        self.panes = panes

    def set_cleanup_policy(self, policy: str) -> None:
        if policy not in _VALID_CLEANUP:
            raise BranchNexusError(
                f"Invalid cleanup policy: {policy}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Use session or persistent.",
            )
        self.cleanup_policy = policy
