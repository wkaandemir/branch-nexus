from __future__ import annotations

import subprocess
from pathlib import Path

from branchnexus.orchestrator import OrchestrationRequest, orchestrate
from branchnexus.terminal import RuntimeKind, TerminalService
from branchnexus.ui.app import AppShell
from branchnexus.ui.screens.runtime_dashboard import RuntimeDashboardScreen
from branchnexus.ui.widgets.runtime_output import RuntimeOutputPanel
from branchnexus.worktree.manager import WorktreeAssignment


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_runtime_smoke_route_flow() -> None:
    shell = AppShell()
    assert shell.router.current() == "runtime"
    assert shell.router.next() == "runtime"


def test_phase2_smoke_orchestrator_still_runs(tmp_path: Path) -> None:
    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[:4] == ["wsl.exe", "-d", "Ubuntu", "--"] and cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(0)
        return _cp(0)

    request = OrchestrationRequest(
        distribution="Ubuntu",
        available_distributions=["Ubuntu"],
        layout="vertical",
        cleanup_policy="session",
        assignments=[
            WorktreeAssignment(pane=1, repo_path=Path("/repo/a"), branch="main"),
            WorktreeAssignment(pane=2, repo_path=Path("/repo/b"), branch="feature"),
        ],
        worktree_base=tmp_path / ".bnx",
    )
    result = orchestrate(request, runner=runner, output=RuntimeOutputPanel())
    assert len(result.worktrees) == 2


def test_phase2_runtime_dashboard_smoke_actions() -> None:
    service = TerminalService(max_terminals=16)
    dashboard = RuntimeDashboardScreen(service, template="4")
    dashboard.bootstrap()
    assert len(dashboard.list_panels()) == 4

    dashboard.set_template("6")
    assert len(dashboard.list_panels()) == 6

    created = dashboard.add_terminal(runtime=RuntimeKind.POWERSHELL)
    dashboard.remove_terminal(created.spec.terminal_id, cleanup="preserve")
    assert len(dashboard.list_panels()) == 6
