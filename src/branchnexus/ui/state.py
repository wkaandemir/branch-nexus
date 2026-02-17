"""Global UI state container."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AppState:
    root_path: str = ""
    remote_repo_url: str = ""
    layout: str = "grid"
    panes: int = 4
    cleanup: str = "session"
    wsl_distribution: str = ""
    runtime_profile: str = "wsl"
    terminal_template: int = 4
    max_terminals: int = 16
    terminal_default_runtime: str = "wsl"
    focused_terminal_id: str = ""
    assignments: dict[int, tuple[str, str]] = field(default_factory=dict)
