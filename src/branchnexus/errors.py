"""Deterministic error model and exit code contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    INVALID_ARGS = 2
    CONFIG_ERROR = 3
    RUNTIME_ERROR = 4
    GIT_ERROR = 5
    TMUX_ERROR = 6
    VALIDATION_ERROR = 7
    UNSUPPORTED_PLATFORM = 8


@dataclass
class BranchNexusError(Exception):
    message: str
    code: ExitCode = ExitCode.RUNTIME_ERROR
    hint: str = ""

    def __str__(self) -> str:
        if self.hint:
            return f"{self.message} Hint: {self.hint}"
        return self.message


def user_facing_error(message: str, *, hint: str = "") -> str:
    if hint:
        return f"Error: {message}. Next step: {hint}"
    return f"Error: {message}."
