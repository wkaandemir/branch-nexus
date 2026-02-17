"""Terminal runtime-v2 domain models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RuntimeKind(str, Enum):
    WSL = "wsl"
    POWERSHELL = "powershell"


class TerminalState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class TerminalSpec:
    terminal_id: str
    title: str
    runtime: RuntimeKind = RuntimeKind.WSL
    repo_path: str = ""
    branch: str = ""


@dataclass
class TerminalInstance:
    spec: TerminalSpec
    state: TerminalState = TerminalState.CREATED
    metadata: dict[str, str] = field(default_factory=dict)

