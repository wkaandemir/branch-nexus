from __future__ import annotations

from branchnexus.terminal import RuntimeKind, TerminalService
from branchnexus.ui.screens.runtime_dashboard import RuntimeDashboardScreen


def test_default_runtime_is_applied_to_new_terminals() -> None:
    service = TerminalService(max_terminals=4, default_runtime=RuntimeKind.WSL)
    dashboard = RuntimeDashboardScreen(service, template="2")
    dashboard.bootstrap()

    assert {panel.runtime for panel in dashboard.list_panels()} == {RuntimeKind.WSL}


def test_terminal_level_runtime_override_is_supported() -> None:
    service = TerminalService(max_terminals=4, default_runtime=RuntimeKind.WSL)
    dashboard = RuntimeDashboardScreen(service, template="2")
    dashboard.bootstrap()
    dashboard.add_terminal(runtime=RuntimeKind.POWERSHELL)

    runtimes = [panel.runtime for panel in dashboard.list_panels()]
    assert RuntimeKind.WSL in runtimes
    assert RuntimeKind.POWERSHELL in runtimes


def test_switch_can_update_runtime_per_terminal() -> None:
    service = TerminalService(max_terminals=4, default_runtime=RuntimeKind.WSL)
    dashboard = RuntimeDashboardScreen(service, template="2")
    dashboard.bootstrap()
    first = dashboard.list_panels()[0]

    dashboard.change_repo_branch(
        first.terminal_id,
        repo_path="/repo/a",
        branch="feature/x",
        runtime=RuntimeKind.POWERSHELL,
    )
    updated = [item for item in dashboard.list_panels() if item.terminal_id == first.terminal_id][0]
    assert updated.runtime == RuntimeKind.POWERSHELL
