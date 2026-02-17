from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.terminal import (
    DirtySwitchDecision,
    RuntimeKind,
    TerminalService,
    TerminalSpec,
    TerminalState,
)

pytestmark = pytest.mark.critical_regression


class _SwitchBackend:
    def __init__(self, *, fail_cwd: str = "") -> None:
        self.fail_cwd = fail_cwd
        self.start_calls: list[tuple[str, RuntimeKind, str | None]] = []
        self.stop_calls: list[str] = []

    def start(self, terminal_id: str, *, runtime: RuntimeKind, cwd: str | None = None) -> object:
        self.start_calls.append((terminal_id, runtime, cwd))
        if self.fail_cwd and cwd == self.fail_cwd:
            raise BranchNexusError("start failed")
        return object()

    def stop(self, terminal_id: str) -> None:
        self.stop_calls.append(terminal_id)


def test_switch_context_reopens_terminal_and_logs_steps() -> None:
    backend = _SwitchBackend()
    service = TerminalService(max_terminals=4, pty_backend=backend)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1", repo_path="/repo/a", branch="main"))
    service.start("t1")

    switched = service.switch_context("t1", repo_path="/repo/b", branch="feature/x")
    assert switched.state == TerminalState.RUNNING
    assert switched.spec.repo_path == "/repo/b"
    assert switched.spec.branch == "feature/x"
    assert "t1" in backend.stop_calls
    assert any(event.step == "switch-complete" for event in service.list_events())


def test_switch_context_reverts_previous_state_on_failure() -> None:
    backend = _SwitchBackend(fail_cwd="/repo/bad")
    service = TerminalService(max_terminals=4, pty_backend=backend)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1", repo_path="/repo/a", branch="main"))
    service.start("t1")

    with pytest.raises(BranchNexusError):
        service.switch_context("t1", repo_path="/repo/bad", branch="feature/x")

    instance = service.list_instances()[0]
    assert instance.spec.repo_path == "/repo/a"
    assert instance.spec.branch == "main"
    assert instance.state == TerminalState.RUNNING


def test_switch_materializes_remote_branch() -> None:
    materialize_calls: list[tuple[str, str]] = []

    def materializer(repo_path: str, remote_branch: str) -> str:
        materialize_calls.append((repo_path, remote_branch))
        return "feature-x"

    service = TerminalService(max_terminals=4, materializer=materializer)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1"))
    service.start("t1")
    switched = service.switch_context("t1", repo_path="/repo/a", branch="origin/feature-x")

    assert switched.spec.branch == "feature-x"
    assert materialize_calls == [("/repo/a", "origin/feature-x")]


def test_dirty_switch_choices_control_behavior() -> None:
    service = TerminalService(max_terminals=4)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1", repo_path="/repo/a", branch="main"))
    service.start("t1")

    with pytest.raises(BranchNexusError):
        service.switch_context(
            "t1",
            repo_path="/repo/b",
            branch="feature/y",
            dirty_checker=lambda _: True,
            dirty_resolver=lambda _: DirtySwitchDecision.CANCEL,
        )

    switched = service.switch_context(
        "t1",
        repo_path="/repo/b",
        branch="feature/y",
        dirty_checker=lambda _: True,
        dirty_resolver=lambda _: DirtySwitchDecision.PRESERVE,
    )
    assert switched.metadata["dirty_switch"] == DirtySwitchDecision.PRESERVE.value
