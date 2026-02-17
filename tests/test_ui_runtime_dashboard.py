from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.terminal import RuntimeKind, TerminalService
from branchnexus.ui.screens.runtime_dashboard import RuntimeDashboardScreen


def test_runtime_dashboard_bootstrap_creates_template_panels() -> None:
    service = TerminalService(max_terminals=16)
    dashboard = RuntimeDashboardScreen(service, template="4")
    dashboard.bootstrap()

    panels = dashboard.list_panels()
    assert len(panels) == 4
    assert panels[0].focused is True


def test_runtime_dashboard_template_switch_supports_catalog_and_custom() -> None:
    service = TerminalService(max_terminals=16)
    dashboard = RuntimeDashboardScreen(service, template="2")
    dashboard.bootstrap()

    assert dashboard.set_template("8") == 8
    assert len(dashboard.list_panels()) == 8

    assert dashboard.set_template("custom", custom_terminal_count=10) == 10
    assert len(dashboard.list_panels()) == 10

    with pytest.raises(BranchNexusError):
        dashboard.set_template("custom", custom_terminal_count=20)


def test_runtime_dashboard_focus_and_runtime_override() -> None:
    service = TerminalService(max_terminals=16)
    dashboard = RuntimeDashboardScreen(service, template="2")
    dashboard.bootstrap()

    added = dashboard.add_terminal(runtime=RuntimeKind.POWERSHELL)
    dashboard.focus_terminal(added.spec.terminal_id)
    focused = [item for item in dashboard.list_panels() if item.focused]
    assert len(focused) == 1
    assert focused[0].runtime == RuntimeKind.POWERSHELL


def test_runtime_dashboard_remove_updates_focus() -> None:
    service = TerminalService(max_terminals=16)
    dashboard = RuntimeDashboardScreen(service, template="2")
    dashboard.bootstrap()

    panels = dashboard.list_panels()
    dashboard.focus_terminal(panels[1].terminal_id)
    dashboard.remove_terminal(panels[1].terminal_id, cleanup="clean")

    remaining = dashboard.list_panels()
    assert len(remaining) == 1
    assert remaining[0].focused is True


def test_runtime_dashboard_restore_snapshot_is_non_destructive_on_invalid_payload() -> None:
    service = TerminalService(max_terminals=16)
    dashboard = RuntimeDashboardScreen(service, template="2")
    dashboard.bootstrap()

    before = [(panel.terminal_id, panel.repo_path, panel.branch) for panel in dashboard.list_panels()]
    invalid_snapshot = {
        "template_count": 2,
        "focused_terminal_id": "bad",
        "terminals": [
            {
                "terminal_id": "t9",
                "title": "Terminal 9",
                "runtime": "wsl",
                "repo_path": "/repo/new",
                "branch": "main",
            },
            "invalid-entry",
        ],
    }

    assert dashboard.restore_snapshot(invalid_snapshot) is False
    after = [(panel.terminal_id, panel.repo_path, panel.branch) for panel in dashboard.list_panels()]
    assert after == before
