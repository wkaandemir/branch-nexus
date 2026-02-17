from __future__ import annotations

import time

import pytest

from branchnexus.terminal import RuntimeKind, TerminalService, TerminalSpec, TerminalState


class _FastBackend:
    def start(self, terminal_id: str, *, runtime: RuntimeKind, cwd: str | None = None) -> object:
        _ = (terminal_id, runtime, cwd)
        return object()

    def stop(self, terminal_id: str) -> None:
        _ = terminal_id


@pytest.mark.performance
def test_switch_context_loop_stays_within_budget() -> None:
    service = TerminalService(max_terminals=4, pty_backend=_FastBackend())
    service.create(TerminalSpec(terminal_id="t1", title="Pane 1", repo_path="/repo/a", branch="main"))
    service.start("t1")

    started = time.perf_counter()
    for index in range(200):
        service.switch_context("t1", repo_path=f"/repo/{index % 3}", branch=f"feature/{index}")
    elapsed = time.perf_counter() - started

    assert service.list_instances()[0].state == TerminalState.RUNNING
    assert elapsed < 2.0, f"switch_context loop exceeded budget: {elapsed:.3f}s"


@pytest.mark.performance
def test_event_recording_throughput_stays_within_budget() -> None:
    service = TerminalService(max_terminals=4)

    started = time.perf_counter()
    for index in range(5000):
        service.record_event("t1", "perf", f"event-{index}")
    elapsed = time.perf_counter() - started

    assert len(service.list_events()) == 5000
    assert elapsed < 2.0, f"event recording exceeded budget: {elapsed:.3f}s"
