"""Runtime output panel and action bindings."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeEvent:
    step: str
    state: str
    message: str


class RuntimeOutputPanel:
    def __init__(
        self,
        *,
        on_retry: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_open_log: Callable[[], None] | None = None,
    ) -> None:
        self.events: list[RuntimeEvent] = []
        self.on_retry = on_retry
        self.on_stop = on_stop
        self.on_open_log = on_open_log

    def record_started(self, step: str, message: str = "") -> None:
        self.events.append(RuntimeEvent(step=step, state="started", message=message))

    def record_success(self, step: str, message: str = "") -> None:
        self.events.append(RuntimeEvent(step=step, state="success", message=message))

    def record_error(self, step: str, message: str) -> None:
        self.events.append(RuntimeEvent(step=step, state="error", message=message))

    def retry(self) -> None:
        if self.on_retry:
            self.on_retry()

    def stop(self) -> None:
        if self.on_stop:
            self.on_stop()

    def open_log(self) -> None:
        if self.on_open_log:
            self.on_open_log()
