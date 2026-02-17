from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.terminal import RuntimeKind, TerminalService, TerminalState
from branchnexus.ui.screens.runtime_dashboard import RuntimeDashboardScreen

pytestmark = pytest.mark.critical_regression


class _FakePtyBackend:
    def __init__(self) -> None:
        self.start_calls: list[tuple[str, RuntimeKind, str | None]] = []
        self.stop_calls: list[str] = []

    def start(self, terminal_id: str, *, runtime: RuntimeKind, cwd: str | None = None) -> object:
        self.start_calls.append((terminal_id, runtime, cwd))
        return object()

    def stop(self, terminal_id: str) -> None:
        self.stop_calls.append(terminal_id)


class _FailingStopBackend(_FakePtyBackend):
    def stop(self, terminal_id: str) -> None:
        from branchnexus.errors import ExitCode

        self.stop_calls.append(terminal_id)
        raise BranchNexusError("stop failed", code=ExitCode.RUNTIME_ERROR)


def test_add_terminal_is_immediate_and_limit_enforced() -> None:
    service = TerminalService(max_terminals=2)
    dashboard = RuntimeDashboardScreen(service, template="2")
    dashboard.bootstrap()

    with pytest.raises(BranchNexusError):
        dashboard.add_terminal()


def test_remove_terminal_stops_process_and_tracks_cleanup_choice() -> None:
    backend = _FakePtyBackend()
    service = TerminalService(max_terminals=4, pty_backend=backend)
    dashboard = RuntimeDashboardScreen(service, template="2")
    dashboard.bootstrap()

    first = dashboard.list_panels()[0]
    dashboard.remove_terminal(first.terminal_id, cleanup="clean")

    assert first.terminal_id in backend.stop_calls
    assert any(event.step == "remove" and "clean" in event.message for event in service.list_events())


def test_remove_terminal_propagates_stop_failure_and_marks_terminal_failed() -> None:
    backend = _FailingStopBackend()
    service = TerminalService(max_terminals=4, pty_backend=backend)
    dashboard = RuntimeDashboardScreen(service, template="2")
    dashboard.bootstrap()

    first = dashboard.list_panels()[0]
    with pytest.raises(BranchNexusError):
        dashboard.remove_terminal(first.terminal_id, cleanup="clean")

    instance = next(item for item in service.list_instances() if item.spec.terminal_id == first.terminal_id)
    assert instance.state == TerminalState.FAILED
    assert any(event.step == "stop-failed" for event in service.list_events())
