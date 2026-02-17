"""Session shutdown and cleanup handler."""

from __future__ import annotations

import logging as py_logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from branchnexus.terminal.models import RuntimeKind, TerminalInstance
from branchnexus.worktree.manager import ManagedWorktree, WorktreeManager

logger = py_logging.getLogger(__name__)


def _validate_terminal_count(value: int) -> int:
    if value < 2 or value > 16:
        raise ValueError(f"Invalid terminal count: {value}")
    return value


class ExitChoice(str, Enum):
    CANCEL = "Vazgec"
    PRESERVE = "Koruyarak Cik"
    CLEAN = "Temizleyerek Cik"


@dataclass
class SessionCleanupResult:
    closed: bool
    cancelled: bool
    removed: list[str]
    preserved_dirty: list[str]


@dataclass(frozen=True)
class SessionTerminalSnapshot:
    terminal_id: str
    title: str
    runtime: RuntimeKind
    repo_path: str
    branch: str


@dataclass(frozen=True)
class RuntimeSessionSnapshot:
    layout: str
    template_count: int
    focused_terminal_id: str
    terminals: list[SessionTerminalSnapshot]

    def to_dict(self) -> dict[str, object]:
        return {
            "layout": self.layout,
            "template_count": self.template_count,
            "focused_terminal_id": self.focused_terminal_id,
            "terminals": [
                {
                    "terminal_id": item.terminal_id,
                    "title": item.title,
                    "runtime": item.runtime.value,
                    "repo_path": item.repo_path,
                    "branch": item.branch,
                }
                for item in self.terminals
            ],
        }


class SessionCleanupHandler:
    def __init__(self, manager: WorktreeManager, prompt: Callable[[list[str]], ExitChoice]) -> None:
        self.manager = manager
        self.prompt = prompt

    def handle_exit(
        self,
        *,
        runner: Callable[..., subprocess.CompletedProcess],
    ) -> SessionCleanupResult:
        if self.manager.cleanup_policy == "persistent":
            logger.debug("Session cleanup skipped due to persistent policy")
            return SessionCleanupResult(
                closed=True,
                cancelled=False,
                removed=[],
                preserved_dirty=[str(item.path) for item in self.manager.managed],
            )

        dirty: list[ManagedWorktree] = []
        clean: list[ManagedWorktree] = []
        for worktree in self.manager.managed:
            if self.manager.check_dirty(worktree, runner=runner):
                dirty.append(worktree)
            else:
                clean.append(worktree)
        logger.debug("Cleanup check complete dirty=%s clean=%s", len(dirty), len(clean))

        if not dirty:
            removed = self.manager.cleanup(runner=runner)
            logger.debug("All worktrees clean; removed=%s", len(removed))
            return SessionCleanupResult(
                closed=True,
                cancelled=False,
                removed=[str(item) for item in removed],
                preserved_dirty=[],
            )

        choice = self.prompt([str(item.path) for item in dirty])
        logger.info("Cleanup prompt result choice=%s dirty_count=%s", choice, len(dirty))
        if choice == ExitChoice.CANCEL:
            return SessionCleanupResult(
                closed=False,
                cancelled=True,
                removed=[],
                preserved_dirty=[str(item.path) for item in dirty],
            )

        if choice == ExitChoice.PRESERVE:
            removed_clean = self.manager.cleanup(runner=runner, selected=clean)
            logger.debug("Preserve dirty worktrees; removed clean=%s", len(removed_clean))
            return SessionCleanupResult(
                closed=True,
                cancelled=False,
                removed=[str(item) for item in removed_clean],
                preserved_dirty=[str(item.path) for item in dirty],
            )

        removed_all = self.manager.cleanup(runner=runner)
        logger.debug("Cleanup forced for all worktrees removed=%s", len(removed_all))
        return SessionCleanupResult(
            closed=True,
            cancelled=False,
            removed=[str(item) for item in removed_all],
            preserved_dirty=[],
        )


def build_runtime_snapshot(
    *,
    layout: str,
    template_count: int,
    terminals: list[TerminalInstance],
    focused_terminal_id: str = "",
) -> RuntimeSessionSnapshot:
    count = _validate_terminal_count(template_count)
    snapshots = [
        SessionTerminalSnapshot(
            terminal_id=item.spec.terminal_id,
            title=item.spec.title,
            runtime=item.spec.runtime,
            repo_path=item.spec.repo_path,
            branch=item.spec.branch,
        )
        for item in terminals
    ]
    return RuntimeSessionSnapshot(
        layout=layout,
        template_count=count,
        focused_terminal_id=focused_terminal_id,
        terminals=snapshots,
    )


def parse_runtime_snapshot(raw: Any) -> RuntimeSessionSnapshot | None:
    if not isinstance(raw, dict):
        return None
    terminals_raw = raw.get("terminals")
    if not isinstance(terminals_raw, list):
        return None
    if not terminals_raw:
        return None

    try:
        template_count = _validate_terminal_count(int(raw.get("template_count", len(terminals_raw))))
    except Exception:
        return None

    terminals: list[SessionTerminalSnapshot] = []
    for item in terminals_raw:
        if not isinstance(item, dict):
            return None
        terminal_id = str(item.get("terminal_id", "")).strip()
        title = str(item.get("title", terminal_id or "Terminal")).strip()
        repo_path = str(item.get("repo_path", "")).strip()
        branch = str(item.get("branch", "")).strip()
        runtime_raw = str(item.get("runtime", RuntimeKind.WSL.value)).strip().lower()
        if runtime_raw == RuntimeKind.POWERSHELL.value:
            runtime = RuntimeKind.POWERSHELL
        elif runtime_raw == RuntimeKind.WSL.value:
            runtime = RuntimeKind.WSL
        else:
            return None
        if not terminal_id:
            return None
        terminals.append(
            SessionTerminalSnapshot(
                terminal_id=terminal_id,
                title=title,
                runtime=runtime,
                repo_path=repo_path,
                branch=branch,
            )
        )

    return RuntimeSessionSnapshot(
        layout=str(raw.get("layout", "grid")),
        template_count=template_count,
        focused_terminal_id=str(raw.get("focused_terminal_id", "")).strip(),
        terminals=terminals,
    )
