from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from branchnexus.git.branch_provider import BranchListResult
from branchnexus.git.repo_discovery import discover_repositories
from branchnexus.orchestrator import OrchestrationRequest, orchestrate
from branchnexus.runtime.wsl_selection import persist_distribution, preload_distribution
from branchnexus.session import ExitChoice, SessionCleanupHandler
from branchnexus.ui.screens.repo_select import PanelAssignmentModel
from branchnexus.ui.widgets.runtime_output import RuntimeOutputPanel
from branchnexus.worktree.manager import WorktreeAssignment, WorktreeManager

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.critical_regression,
]


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _fake_branch_provider(_: str) -> BranchListResult:
    return BranchListResult(branches=["main", "feature-x"])


def _init_repo(path: Path) -> None:
    (path / ".git").mkdir(parents=True)


def test_wsl_selection_persists_and_restores(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    persist_distribution("Ubuntu", config_path)
    assert preload_distribution(["Ubuntu", "Debian"], config_path) == "Ubuntu"


def test_repo_discovery_and_local_branch_mapping(tmp_path: Path) -> None:
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    _init_repo(repo_a)
    _init_repo(repo_b)

    repos = [str(path) for path in discover_repositories(tmp_path)]
    assert repos == sorted([str(repo_a.resolve()), str(repo_b.resolve())])

    model = PanelAssignmentModel(panes=2)
    model.set_assignment(1, repos[0], _fake_branch_provider(repos[0]).branches[0])
    model.set_assignment(2, repos[1], _fake_branch_provider(repos[1]).branches[1])
    assert model.is_complete() is True


def test_orchestration_routes_commands_through_wsl(tmp_path: Path) -> None:
    executed: list[list[str]] = []

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        executed.append(cmd)
        if cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] and cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(0, "/usr/bin/tmux\n")
        return _cp(0)

    request = OrchestrationRequest(
        distribution="Ubuntu",
        available_distributions=["Ubuntu"],
        layout="grid",
        cleanup_policy="session",
        assignments=[
            WorktreeAssignment(pane=1, repo_path=Path("/repo/a"), branch="main"),
            WorktreeAssignment(pane=2, repo_path=Path("/repo/b"), branch="feature-x"),
        ],
        worktree_base=tmp_path / ".bnx",
    )
    result = orchestrate(request, runner=runner, output=RuntimeOutputPanel())

    assert len(result.worktrees) == 2
    assert all(cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] for cmd in result.executed_commands)


def test_session_cleanup_requires_explicit_dirty_confirmation(tmp_path: Path) -> None:
    manager = WorktreeManager(tmp_path / ".bnx", cleanup_policy="session")
    manager.add_worktree(
        WorktreeAssignment(pane=1, repo_path=Path("/repo/a"), branch="main"),
        runner=lambda *args, **kwargs: _cp(0),
    )

    remove_calls = {"count": 0}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-2:] == ["status", "--porcelain"]:
            return _cp(0, "M dirty.py\n")
        if "remove" in cmd:
            remove_calls["count"] += 1
        return _cp(0)

    cancelled = SessionCleanupHandler(manager, prompt=lambda _: ExitChoice.CANCEL).handle_exit(runner=runner)
    assert cancelled.cancelled is True
    assert remove_calls["count"] == 0

    preserved = SessionCleanupHandler(manager, prompt=lambda _: ExitChoice.PRESERVE).handle_exit(runner=runner)
    assert preserved.closed is True
    assert preserved.preserved_dirty

    cleaned = SessionCleanupHandler(manager, prompt=lambda _: ExitChoice.CLEAN).handle_exit(runner=runner)
    assert cleaned.closed is True
