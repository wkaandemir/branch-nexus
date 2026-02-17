from __future__ import annotations

from branchnexus.ui.widgets.runtime_output import RuntimeOutputPanel


def test_runtime_output_records_step_events_in_order() -> None:
    panel = RuntimeOutputPanel()
    panel.record_started("discover", "starting")
    panel.record_success("discover", "done")
    panel.record_error("worktree", "failed")

    assert [(event.step, event.state) for event in panel.events] == [
        ("discover", "started"),
        ("discover", "success"),
        ("worktree", "error"),
    ]


def test_runtime_actions_invoke_callbacks() -> None:
    flags = {"retry": False, "stop": False, "log": False}
    panel = RuntimeOutputPanel(
        on_retry=lambda: flags.__setitem__("retry", True),
        on_stop=lambda: flags.__setitem__("stop", True),
        on_open_log=lambda: flags.__setitem__("log", True),
    )

    panel.retry()
    panel.stop()
    panel.open_log()
    assert flags == {"retry": True, "stop": True, "log": True}
