from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.worktree.manager import WorktreeAssignment, WorktreeManager

pytestmark = pytest.mark.critical_regression


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_build_path_is_deterministic(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / ".bnx", cleanup_policy="session")
    assignment = WorktreeAssignment(pane=1, repo_path=Path("/repos/app"), branch="feature/add-x")
    path = manager.build_worktree_path(assignment)
    assert path.as_posix().endswith("app/pane-1-feature-add-x")


def test_materialize_calls_git_worktree_add(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        commands.append(cmd)
        return _cp(0)

    manager = WorktreeManager(tmp_path / ".bnx")
    assignments = [
        WorktreeAssignment(pane=2, repo_path=Path("/repos/a"), branch="main"),
        WorktreeAssignment(pane=1, repo_path=Path("/repos/b"), branch="feature"),
    ]
    created = manager.materialize(assignments, runner=runner)
    assert [item.pane for item in created] == [1, 2]
    assert all("worktree" in cmd for cmd in commands)


def test_cleanup_honors_persistent_policy(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / ".bnx", cleanup_policy="persistent")
    removed = manager.cleanup(runner=lambda *args, **kwargs: _cp(0))
    assert removed == []


def test_dirty_check_raises_when_git_fails(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / ".bnx")
    managed = manager.add_worktree(
        WorktreeAssignment(pane=1, repo_path=Path("/repo"), branch="main"),
        runner=lambda *args, **kwargs: _cp(0),
    )

    with pytest.raises(BranchNexusError):
        manager.check_dirty(managed, runner=lambda *args, **kwargs: _cp(1, stderr="boom"))


def test_add_worktree_reuses_existing_matching_branch(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / ".bnx")
    assignment = WorktreeAssignment(pane=1, repo_path=Path("/repos/a"), branch="main")
    target = manager.build_worktree_path(assignment)
    Path(target).mkdir(parents=True, exist_ok=True)

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[:3] == ["git", "-C", str(target)] and cmd[3:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return _cp(0, "main\n")
        if "worktree" in cmd and "add" in cmd:
            raise AssertionError("worktree add should not run for reusable path")
        return _cp(0)

    managed = manager.add_worktree(assignment, runner=runner)
    assert str(managed.path) == str(target)
    assert managed.branch == "main"


def test_add_worktree_raises_on_existing_mismatched_branch(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / ".bnx")
    assignment = WorktreeAssignment(pane=1, repo_path=Path("/repos/a"), branch="main")
    target = manager.build_worktree_path(assignment)
    Path(target).mkdir(parents=True, exist_ok=True)

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[:3] == ["git", "-C", str(target)] and cmd[3:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return _cp(0, "feature\n")
        return _cp(0)

    with pytest.raises(BranchNexusError):
        manager.add_worktree(assignment, runner=runner)


def test_add_worktree_reuses_existing_branch_worktree_path(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / ".bnx")
    assignment = WorktreeAssignment(pane=1, repo_path=Path("/repos/a"), branch="main")
    existing = tmp_path / ".bnx" / "a" / "pane-4-main"
    existing.mkdir(parents=True, exist_ok=True)
    repo_cmd = manager._command_path(assignment.repo_path)

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[:4] == ["git", "-C", repo_cmd, "worktree"] and cmd[4:] == ["list", "--porcelain"]:
            return _cp(
                0,
                f"worktree {existing.as_posix()}\nHEAD deadbeef\nbranch refs/heads/main\n",
            )
        if cmd[:3] == ["git", "-C", str(existing)] and cmd[3:] == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return _cp(0, "main\n")
        if "worktree" in cmd and "add" in cmd:
            raise AssertionError("worktree add should not run when branch already has reusable worktree")
        return _cp(0)

    managed = manager.add_worktree(assignment, runner=runner)
    assert str(managed.path) == str(existing)
    assert managed.branch == "main"


def test_add_worktree_raises_when_branch_used_outside_managed_base(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / ".bnx")
    assignment = WorktreeAssignment(pane=1, repo_path=Path("/repos/a"), branch="main")
    repo_cmd = manager._command_path(assignment.repo_path)

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[:4] == ["git", "-C", repo_cmd, "worktree"] and cmd[4:] == ["list", "--porcelain"]:
            return _cp(
                0,
                "worktree /repos/a\nHEAD deadbeef\nbranch refs/heads/main\n",
            )
        return _cp(0)

    with pytest.raises(BranchNexusError):
        manager.add_worktree(assignment, runner=runner)
