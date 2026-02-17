"""Terminal runtime-v2 domain package."""

from .models import RuntimeKind, TerminalInstance, TerminalSpec, TerminalState
from .pty_backend import PtyBackend, PtyHandle, build_shell_command
from .service import DirtySwitchDecision, TerminalEvent, TerminalService

__all__ = [
    "build_shell_command",
    "DirtySwitchDecision",
    "PtyBackend",
    "PtyHandle",
    "RuntimeKind",
    "TerminalEvent",
    "TerminalInstance",
    "TerminalService",
    "TerminalSpec",
    "TerminalState",
]
