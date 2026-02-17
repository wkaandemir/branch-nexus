from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.terminal import RuntimeKind, TerminalService, TerminalSpec, TerminalState


def test_create_start_switch_and_stop_terminal() -> None:
    service = TerminalService(max_terminals=4)
    instance = service.create(TerminalSpec(terminal_id="t1", title="Pane 1"))
    assert instance.state == TerminalState.CREATED
    assert instance.spec.runtime == RuntimeKind.WSL

    service.start("t1")
    assert service.list_instances()[0].state == TerminalState.RUNNING

    switched = service.switch_context(
        "t1",
        repo_path="/work/repo-a",
        branch="feature/x",
        runtime=RuntimeKind.POWERSHELL,
    )
    assert switched.spec.repo_path == "/work/repo-a"
    assert switched.spec.branch == "feature/x"
    assert switched.spec.runtime == RuntimeKind.POWERSHELL
    assert switched.state == TerminalState.RUNNING

    service.stop("t1")
    assert service.list_instances()[0].state == TerminalState.STOPPED


def test_rejects_duplicate_terminal_ids() -> None:
    service = TerminalService(max_terminals=4)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1"))
    with pytest.raises(BranchNexusError):
        service.create(TerminalSpec(terminal_id="t1", title="Pane 1 duplicate"))


def test_enforces_max_terminal_limit() -> None:
    service = TerminalService(max_terminals=2)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1"))
    service.create(TerminalSpec(terminal_id="t2", title="Pane 2"))
    with pytest.raises(BranchNexusError):
        service.create(TerminalSpec(terminal_id="t3", title="Pane 3"))


def test_switch_context_requires_repo_and_branch() -> None:
    service = TerminalService(max_terminals=4)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1"))
    with pytest.raises(BranchNexusError):
        service.switch_context("t1", repo_path="", branch="main")
    with pytest.raises(BranchNexusError):
        service.switch_context("t1", repo_path="/repo", branch="")

