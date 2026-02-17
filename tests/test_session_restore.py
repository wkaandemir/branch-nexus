from __future__ import annotations

from pathlib import Path

from branchnexus.config import AppConfig, load_config
from branchnexus.session import build_runtime_snapshot, parse_runtime_snapshot
from branchnexus.terminal import RuntimeKind, TerminalService, TerminalSpec
from branchnexus.ui.app import build_state_from_config, launch_runtime_dashboard


def test_runtime_snapshot_roundtrip() -> None:
    service = TerminalService(max_terminals=4)
    service.create(TerminalSpec(terminal_id="t1", title="Terminal 1", runtime=RuntimeKind.WSL, repo_path="/repo/a", branch="main"))
    service.create(
        TerminalSpec(
            terminal_id="t2",
            title="Terminal 2",
            runtime=RuntimeKind.POWERSHELL,
            repo_path="/repo/b",
            branch="feature/x",
        )
    )

    snapshot = build_runtime_snapshot(
        layout="grid",
        template_count=2,
        terminals=service.list_instances(),
        focused_terminal_id="t2",
    ).to_dict()
    parsed = parse_runtime_snapshot(snapshot)

    assert parsed is not None
    assert parsed.layout == "grid"
    assert parsed.template_count == 2
    assert parsed.focused_terminal_id == "t2"
    assert len(parsed.terminals) == 2


def test_launch_runtime_dashboard_restores_previous_session(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config = AppConfig(
        default_panes=4,
        session_restore_enabled=True,
        last_session={
            "layout": "grid",
            "template_count": 2,
            "focused_terminal_id": "t2",
            "terminals": [
                {
                    "terminal_id": "t1",
                    "title": "Terminal 1",
                    "runtime": "wsl",
                    "repo_path": "/repo/a",
                    "branch": "main",
                },
                {
                    "terminal_id": "t2",
                    "title": "Terminal 2",
                    "runtime": "powershell",
                    "repo_path": "/repo/b",
                    "branch": "feature/x",
                },
            ],
        },
    )
    state = build_state_from_config(config)
    code = launch_runtime_dashboard(config=config, state=state, config_path=config_path)

    assert code == 0
    assert state.terminal_template == 2
    assert state.focused_terminal_id == "t2"

    loaded = load_config(config_path)
    assert loaded.last_session["template_count"] == 2
    assert len(loaded.last_session["terminals"]) == 2


def test_launch_runtime_dashboard_falls_back_when_snapshot_invalid(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config = AppConfig(
        default_panes=4,
        session_restore_enabled=True,
        last_session={"broken": "snapshot"},
    )
    state = build_state_from_config(config)
    code = launch_runtime_dashboard(config=config, state=state, config_path=config_path)

    assert code == 0
    assert state.terminal_template == 4
    assert state.focused_terminal_id == "t1"
