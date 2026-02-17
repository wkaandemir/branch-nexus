from __future__ import annotations

from branchnexus.ui.app import AppShell
from branchnexus.ui.state import AppState


def test_app_shell_routes_between_steps() -> None:
    shell = AppShell()
    assert shell.router.current() == "runtime"
    assert shell.router.next() == "runtime"
    assert shell.router.prev() == "runtime"


def test_app_shell_preserves_global_state() -> None:
    state = AppState(root_path="/repos", panes=4)
    shell = AppShell(state=state)
    shell.state.layout = "horizontal"
    assert state.layout == "horizontal"


def test_close_guard_can_block_shutdown() -> None:
    shell = AppShell()
    shell.set_close_guard(lambda: False)
    assert shell.close() is False
    assert shell.closed is False
