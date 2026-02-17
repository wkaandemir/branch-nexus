from __future__ import annotations

from pathlib import Path

from branchnexus.config import AppConfig
from branchnexus.ui import app as app_module


def test_launch_app_always_uses_runtime_dashboard(monkeypatch) -> None:
    config = AppConfig(default_panes=6, terminal_max_count=12, terminal_default_runtime="wsl")
    seen: dict[str, object] = {}

    monkeypatch.setattr(app_module, "load_config", lambda _path: config)

    def fake_launch_runtime_dashboard(*, config: AppConfig, state, config_path, run_ui: bool) -> int:  # type: ignore[no-untyped-def]
        seen["config"] = config
        seen["state"] = state
        seen["config_path"] = config_path
        seen["run_ui"] = run_ui
        return 7

    monkeypatch.setattr(app_module, "launch_runtime_dashboard", fake_launch_runtime_dashboard)

    result = app_module.launch_app(config_path=Path("/tmp/config.toml"))

    assert result == 7
    assert seen["config"] is config
    assert seen["run_ui"] is True
    assert seen["config_path"] == Path("/tmp/config.toml")


def test_launch_app_with_fresh_start_resets_before_dashboard(monkeypatch) -> None:
    config = AppConfig(default_panes=4, terminal_max_count=8, terminal_default_runtime="wsl")
    seen: dict[str, object] = {}

    monkeypatch.setattr(app_module, "load_config", lambda _path: config)

    def fake_fresh_reset(*, config: AppConfig, config_path, wsl_distribution: str = "") -> list[str]:  # type: ignore[no-untyped-def]
        seen["fresh_config"] = config
        seen["fresh_config_path"] = config_path
        seen["fresh_wsl_distribution"] = wsl_distribution
        return []

    def fake_launch_runtime_dashboard(*, config: AppConfig, state, config_path, run_ui: bool) -> int:  # type: ignore[no-untyped-def]
        seen["dashboard_config"] = config
        seen["run_ui"] = run_ui
        return 9

    monkeypatch.setattr(app_module, "_run_fresh_start_reset", fake_fresh_reset)
    monkeypatch.setattr(app_module, "launch_runtime_dashboard", fake_launch_runtime_dashboard)

    result = app_module.launch_app(config_path=Path("/tmp/config.toml"), fresh_start=True)

    assert result == 9
    assert seen["fresh_config"] is config
    assert seen["fresh_config_path"] == Path("/tmp/config.toml")
    assert seen["fresh_wsl_distribution"] == ""
    assert seen["dashboard_config"] is config
    assert seen["run_ui"] is True
