from __future__ import annotations

from pathlib import Path, PurePosixPath

import branchnexus.ui.services.session_manager as session_manager
from branchnexus.config import AppConfig


def test_resolve_wsl_workspace_root_defaults_to_wsl_home(monkeypatch) -> None:
    monkeypatch.setattr(
        session_manager,
        "resolve_wsl_home_directory",
        lambda **kwargs: PurePosixPath("/home/demo"),
    )
    root = session_manager.resolve_wsl_workspace_root("Ubuntu", "")
    assert root == "/home/demo/branchnexus-workspace"


def test_resolve_wsl_workspace_root_forces_linux_for_mnt_paths(monkeypatch) -> None:
    monkeypatch.setattr(
        session_manager,
        "resolve_wsl_home_directory",
        lambda **kwargs: PurePosixPath("/home/demo"),
    )
    root = session_manager.resolve_wsl_workspace_root("Ubuntu", "/mnt/c/repos")
    assert root == "/home/demo/branchnexus-workspace"


def test_resolve_wsl_workspace_root_forces_linux_for_windows_configured_path(monkeypatch) -> None:
    monkeypatch.setattr(
        session_manager,
        "resolve_wsl_home_directory",
        lambda **kwargs: PurePosixPath("/home/demo"),
    )
    monkeypatch.setattr(session_manager, "to_wsl_path", lambda *_args, **_kwargs: "/mnt/c/repos")
    root = session_manager.resolve_wsl_workspace_root("Ubuntu", r"C:\repos")
    assert root == "/home/demo/branchnexus-workspace"


def test_default_workspace_path_uses_userprofile(monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", r"C:\Users\demo")
    path = session_manager.default_workspace_path()
    assert path is not None
    assert str(path).replace("/", "\\").endswith(r"Users\demo\branchnexus-workspace")


def test_is_safe_reset_path() -> None:
    assert session_manager.is_safe_reset_path("/home/demo/branchnexus-workspace")
    assert not session_manager.is_safe_reset_path("/home/demo/projects")


def test_clear_fresh_start_config_resets_fields() -> None:
    cfg = AppConfig(
        default_root="/work",
        remote_repo_url="https://github.com/org/repo.git",
        github_token="ghp_secret",
        github_repositories_cache=[{"full_name": "org/repo", "clone_url": "https://github.com/org/repo.git"}],
        github_branches_cache={"org/repo": ["main"]},
        default_layout="vertical",
        default_panes=6,
        cleanup_policy="persistent",
        tmux_auto_install=False,
        runtime_profile="wsl",
        wsl_distribution="Ubuntu",
        terminal_default_runtime="powershell",
        terminal_max_count=12,
        session_restore_enabled=False,
        last_session={"layout": "grid"},
        presets={"x": {"layout": "grid", "panes": 3, "cleanup": "session"}},
        command_hooks={"pane-1": ["echo 1"]},
    )
    session_manager.clear_fresh_start_config(cfg)
    assert cfg.default_root == ""
    assert cfg.remote_repo_url == ""
    assert cfg.github_token == ""
    assert cfg.default_layout == "grid"
    assert cfg.default_panes == 4
    assert cfg.cleanup_policy == "session"
    assert cfg.terminal_default_runtime == "wsl"
    assert cfg.terminal_max_count == 16
    assert cfg.last_session == {}
    assert cfg.presets == {}
    assert cfg.command_hooks == {}


def test_reset_workspace_clears_config_and_removes_workspaces(tmp_path: Path, monkeypatch) -> None:
    windows_workspace = tmp_path / "windows-workspace"
    windows_workspace.mkdir()
    marker = windows_workspace / "data.txt"
    marker.write_text("payload", encoding="utf-8")

    cfg = AppConfig(
        default_root="/home/demo/branchnexus-workspace",
        remote_repo_url="https://github.com/org/repo.git",
        github_token="ghp_secret",
        wsl_distribution="Ubuntu",
    )
    monkeypatch.setattr(session_manager, "default_workspace_path", lambda: windows_workspace)
    monkeypatch.setattr(
        session_manager,
        "resolve_wsl_workspace_root",
        lambda distribution, configured_root: "/home/demo/branchnexus-workspace",
    )
    monkeypatch.setattr(session_manager, "resolve_fresh_distribution", lambda configured: "Ubuntu")
    monkeypatch.setattr(
        session_manager,
        "run_wsl_probe_script",
        lambda **kwargs: None,
    )

    warnings = session_manager.reset_workspace(config=cfg, config_path=tmp_path / "config.toml")
    assert warnings == []
    assert not windows_workspace.exists()
    assert cfg.default_root == ""
    assert cfg.remote_repo_url == ""
    assert cfg.github_token == ""
