from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.git.remote_provider import CombinedBranchSet
from branchnexus.terminal import (
    DirtySwitchDecision,
    RuntimeKind,
    TerminalService,
    TerminalSpec,
    TerminalState,
)


class _SpyBackend:
    def __init__(self, *, failing_cwd: str = "") -> None:
        self.failing_cwd = failing_cwd
        self.start_calls: list[tuple[str, RuntimeKind, str | None]] = []
        self.stop_calls: list[str] = []

    def start(self, terminal_id: str, *, runtime: RuntimeKind, cwd: str | None = None) -> object:
        self.start_calls.append((terminal_id, runtime, cwd))
        if self.failing_cwd and cwd == self.failing_cwd:
            raise RuntimeError("backend start failed")
        return object()

    def stop(self, terminal_id: str) -> None:
        self.stop_calls.append(terminal_id)


class _LegacyBranchPayload:
    local = ["feature/b", "main", "feature/a"]
    remote = ("origin/main", "origin/feature-b")
    warning = "degraded"


def test_list_branches_requires_non_empty_repo_path() -> None:
    service = TerminalService(max_terminals=4)

    with pytest.raises(BranchNexusError) as exc:
        service.list_branches("   ")

    assert exc.value.code == ExitCode.VALIDATION_ERROR


def test_list_branches_normalizes_legacy_payload_shape() -> None:
    service = TerminalService(max_terminals=4, branch_provider=lambda _: _LegacyBranchPayload())

    result = service.list_branches("/repo")

    assert result == CombinedBranchSet(
        local=["feature/a", "feature/b", "main"],
        remote=["origin/feature-b", "origin/main"],
        warning="degraded",
    )


def test_restart_stops_then_starts_terminal() -> None:
    backend = _SpyBackend()
    service = TerminalService(max_terminals=4, pty_backend=backend)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1"))
    service.start("t1")

    restarted = service.restart("t1")

    assert restarted.state == TerminalState.RUNNING
    assert backend.stop_calls == ["t1"]
    assert [call[0] for call in backend.start_calls] == ["t1", "t1"]


def test_remove_rejects_invalid_cleanup_policy() -> None:
    service = TerminalService(max_terminals=4)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1"))

    with pytest.raises(BranchNexusError) as exc:
        service.remove("t1", cleanup="archive")

    assert exc.value.code == ExitCode.VALIDATION_ERROR


def test_dirty_switch_defaults_to_cancel_without_resolver() -> None:
    service = TerminalService(max_terminals=4)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1", repo_path="/repo/a", branch="main"))
    service.start("t1")

    with pytest.raises(BranchNexusError):
        service.switch_context("t1", repo_path="/repo/b", branch="feature/x", dirty_checker=lambda _: True)

    instance = service.list_instances()[0]
    assert instance.spec.repo_path == "/repo/a"
    assert instance.spec.branch == "main"


@pytest.mark.parametrize(
    ("raw_decision", "expected"),
    [
        (" Preserve ", DirtySwitchDecision.PRESERVE.value),
        ("CLEAN", DirtySwitchDecision.CLEAN.value),
    ],
)
def test_dirty_switch_normalizes_string_decisions(raw_decision: str, expected: str) -> None:
    service = TerminalService(max_terminals=4)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1", repo_path="/repo/a", branch="main"))
    service.start("t1")

    switched = service.switch_context(
        "t1",
        repo_path="/repo/b",
        branch="feature/x",
        dirty_checker=lambda _: True,
        dirty_resolver=lambda _: raw_decision,
    )

    assert switched.metadata["dirty_switch"] == expected


def test_switch_context_wraps_unexpected_backend_errors_and_restores_state() -> None:
    backend = _SpyBackend(failing_cwd="/repo/bad")
    service = TerminalService(max_terminals=4, pty_backend=backend)
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1", repo_path="/repo/a", branch="main"))
    service.start("t1")

    with pytest.raises(BranchNexusError) as exc:
        service.switch_context("t1", repo_path="/repo/bad", branch="feature/x")

    instance = service.list_instances()[0]
    assert exc.value.code == ExitCode.RUNTIME_ERROR
    assert "backend start failed" in exc.value.hint
    assert instance.spec.repo_path == "/repo/a"
    assert instance.spec.branch == "main"
    assert instance.state == TerminalState.RUNNING


def test_record_event_concurrent_writers_do_not_drop_messages() -> None:
    service = TerminalService(max_terminals=4)

    def writer(index: int) -> None:
        service.record_event("t1", "concurrent", f"event-{index}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(writer, range(200)))

    events = service.list_events()
    assert len(events) == 200
    assert {event.message for event in events} >= {"event-0", "event-199"}
