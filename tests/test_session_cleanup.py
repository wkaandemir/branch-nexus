from __future__ import annotations

import subprocess
from pathlib import Path

from branchnexus.session import ExitChoice, SessionCleanupHandler
from branchnexus.worktree.manager import WorktreeAssignment, WorktreeManager


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _make_manager(tmp_path: Path, cleanup_policy: str = "session") -> WorktreeManager:
    manager = WorktreeManager(tmp_path / ".bnx", cleanup_policy=cleanup_policy)
    manager.add_worktree(
        WorktreeAssignment(pane=1, repo_path=Path("/repo/a"), branch="main"),
        runner=lambda *args, **kwargs: _cp(0),
    )
    manager.add_worktree(
        WorktreeAssignment(pane=2, repo_path=Path("/repo/b"), branch="feature"),
        runner=lambda *args, **kwargs: _cp(0),
    )
    return manager


def test_session_policy_cleans_all_when_no_dirty(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-2:] == ["status", "--porcelain"]:
            return _cp(0, "")
        return _cp(0)

    result = SessionCleanupHandler(manager, prompt=lambda _: ExitChoice.CLEAN).handle_exit(runner=runner)
    assert result.closed is True
    assert len(result.removed) == 2


def test_persistent_policy_skips_cleanup(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path, cleanup_policy="persistent")
    result = SessionCleanupHandler(manager, prompt=lambda _: ExitChoice.CLEAN).handle_exit(
        runner=lambda *args, **kwargs: _cp(0)
    )
    assert result.closed is True
    assert result.removed == []


def test_dirty_cancel_keeps_session_open(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-2:] == ["status", "--porcelain"]:
            return _cp(0, "M file.py\n")
        return _cp(0)

    result = SessionCleanupHandler(manager, prompt=lambda _: ExitChoice.CANCEL).handle_exit(runner=runner)
    assert result.cancelled is True
    assert result.closed is False


def test_dirty_preserve_cleans_only_clean_worktrees(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-2:] == ["status", "--porcelain"] and "pane-1" in cmd[2]:
            return _cp(0, "M dirty.txt\n")
        if cmd[-2:] == ["status", "--porcelain"]:
            return _cp(0, "")
        return _cp(0)

    result = SessionCleanupHandler(manager, prompt=lambda _: ExitChoice.PRESERVE).handle_exit(runner=runner)
    assert result.closed is True
    assert len(result.removed) == 1
    assert len(result.preserved_dirty) == 1


def test_dirty_clean_removes_all_with_explicit_confirm(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-2:] == ["status", "--porcelain"]:
            return _cp(0, "M dirty.txt\n")
        return _cp(0)

    result = SessionCleanupHandler(manager, prompt=lambda _: ExitChoice.CLEAN).handle_exit(runner=runner)
    assert result.closed is True
    assert len(result.removed) == 2
    assert result.preserved_dirty == []
