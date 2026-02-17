from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.orchestrator import OrchestrationRequest, orchestrate
from branchnexus.ui.widgets.runtime_output import RuntimeOutputPanel
from branchnexus.worktree.manager import ManagedWorktree, WorktreeAssignment

pytestmark = pytest.mark.critical_regression


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_orchestrator_runs_steps_to_tmux(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        commands.append(cmd)
        if cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] and cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(0, "/usr/bin/tmux")
        return _cp(0)

    output = RuntimeOutputPanel()
    request = OrchestrationRequest(
        distribution="Ubuntu",
        available_distributions=["Ubuntu"],
        layout="grid",
        cleanup_policy="session",
        assignments=[
            WorktreeAssignment(pane=1, repo_path=Path("/repo/a"), branch="main"),
            WorktreeAssignment(pane=2, repo_path=Path("/repo/b"), branch="feature"),
        ],
        worktree_base=tmp_path / ".bnx",
    )

    result = orchestrate(request, runner=runner, output=output)
    assert len(result.worktrees) == 2
    assert any(cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] for cmd in result.executed_commands)
    assert [event.state for event in output.events if event.step == "tmux-layout"][-1] == "success"


def test_orchestrator_blocks_invalid_distribution(tmp_path: Path) -> None:
    request = OrchestrationRequest(
        distribution="Missing",
        available_distributions=["Ubuntu"],
        layout="grid",
        cleanup_policy="session",
        assignments=[],
        worktree_base=tmp_path,
    )
    with pytest.raises(BranchNexusError):
        orchestrate(request, runner=lambda *args, **kwargs: _cp(0))


def test_orchestrator_reports_tmux_failures(tmp_path: Path) -> None:
    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] and cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(0)
        if cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] and "split-window" in cmd:
            return _cp(1, stderr="split failed")
        return _cp(0)

    request = OrchestrationRequest(
        distribution="Ubuntu",
        available_distributions=["Ubuntu"],
        layout="horizontal",
        cleanup_policy="session",
        assignments=[
            WorktreeAssignment(pane=1, repo_path=Path("/repo/a"), branch="main"),
            WorktreeAssignment(pane=2, repo_path=Path("/repo/a"), branch="feature"),
        ],
        worktree_base=tmp_path / ".bnx",
    )

    with pytest.raises(BranchNexusError):
        orchestrate(request, runner=runner, output=RuntimeOutputPanel())


def test_orchestrator_recreates_existing_tmux_session_on_duplicate_error(tmp_path: Path) -> None:
    new_session_attempts = {"count": 0}
    kill_attempted = {"called": False}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] and cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(0)
        if cmd[:6] == ["wsl.exe", "-d", "Ubuntu", "--", "tmux", "new-session"]:
            new_session_attempts["count"] += 1
            if new_session_attempts["count"] == 1:
                return _cp(1, stderr="duplicate session: branchnexus")
            return _cp(0)
        if cmd[:6] == ["wsl.exe", "-d", "Ubuntu", "--", "tmux", "kill-session"]:
            kill_attempted["called"] = True
            return _cp(0)
        return _cp(0)

    request = OrchestrationRequest(
        distribution="Ubuntu",
        available_distributions=["Ubuntu"],
        layout="horizontal",
        cleanup_policy="session",
        assignments=[
            WorktreeAssignment(pane=1, repo_path=Path("/repo/a"), branch="main"),
            WorktreeAssignment(pane=2, repo_path=Path("/repo/a"), branch="feature"),
        ],
        worktree_base=tmp_path / ".bnx",
    )

    result = orchestrate(request, runner=runner, output=RuntimeOutputPanel())
    assert len(result.worktrees) == 2
    assert new_session_attempts["count"] == 2
    assert kill_attempted["called"] is True


def test_orchestrator_materializes_remote_branch_before_worktree(tmp_path: Path) -> None:
    seen_branch_track = {"called": False}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] and cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(0)
        if cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] and "branch" in cmd and "--list" in cmd and "feature-x" in cmd:
            return _cp(0, "")
        if (
            cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"]
            and "branch" in cmd
            and "--track" in cmd
            and "feature-x" in cmd
            and "origin/feature-x" in cmd
        ):
            seen_branch_track["called"] = True
            return _cp(0)
        return _cp(0)

    request = OrchestrationRequest(
        distribution="Ubuntu",
        available_distributions=["Ubuntu"],
        layout="horizontal",
        cleanup_policy="session",
        assignments=[
            WorktreeAssignment(
                pane=1,
                repo_path=Path("/repo/a"),
                branch="origin/feature-x",
            ),
            WorktreeAssignment(
                pane=2,
                repo_path=Path("/repo/a"),
                branch="main",
            ),
        ],
        worktree_base=tmp_path / ".bnx",
    )

    result = orchestrate(request, runner=runner, output=RuntimeOutputPanel())
    assert seen_branch_track["called"] is True
    assert len(result.worktrees) == 2


def test_orchestrator_rolls_back_worktrees_when_tmux_fails(tmp_path: Path) -> None:
    class _Manager:
        cleanup_policy = "persistent"

        def __init__(self) -> None:
            self.cleaned = False
            self.cleaned_selected: list[ManagedWorktree] = []

        def materialize(self, assignments: list[WorktreeAssignment], runner: object) -> list[ManagedWorktree]:
            return [
                ManagedWorktree(
                    pane=item.pane,
                    repo_path=item.repo_path,
                    branch=item.branch,
                    path=tmp_path / f"pane-{item.pane}",
                )
                for item in assignments
            ]

        def cleanup(
            self,
            runner: object,
            *,
            force: bool = True,
            selected: list[ManagedWorktree] | None = None,
            ignore_policy: bool = False,
        ) -> list[Path]:
            self.cleaned = True
            self.cleaned_selected = list(selected or [])
            assert ignore_policy is True
            return [Path(item.path) for item in self.cleaned_selected]

    manager = _Manager()

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] and cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(0)
        if cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] and "split-window" in cmd:
            return _cp(1, stderr="split failed")
        return _cp(0)

    request = OrchestrationRequest(
        distribution="Ubuntu",
        available_distributions=["Ubuntu"],
        layout="horizontal",
        cleanup_policy="persistent",
        assignments=[
            WorktreeAssignment(pane=1, repo_path=Path("/repo/a"), branch="main"),
            WorktreeAssignment(pane=2, repo_path=Path("/repo/a"), branch="feature"),
        ],
        worktree_base=tmp_path / ".bnx",
    )

    with pytest.raises(BranchNexusError):
        orchestrate(request, runner=runner, output=RuntimeOutputPanel(), manager=manager)
    assert manager.cleaned is True
    assert len(manager.cleaned_selected) == 2
