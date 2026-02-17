from __future__ import annotations

from pathlib import Path

from branchnexus.config import AppConfig, load_config, save_config, set_wsl_distribution


def test_load_defaults_when_config_missing(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    cfg = load_config(path)
    assert cfg.default_layout == "grid"
    assert cfg.default_panes == 4
    assert cfg.cleanup_policy == "session"
    assert cfg.terminal_default_runtime == "wsl"
    assert cfg.terminal_max_count == 16
    assert cfg.session_restore_enabled is True
    assert cfg.last_session == {}


def test_config_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    original = AppConfig(
        default_root="/repos",
        remote_repo_url="https://github.com/org/repo.git",
        github_token="ghp_saved_token",
        github_repositories_cache=[
            {"full_name": "org/repo-a", "clone_url": "https://github.com/org/repo-a.git"},
            {"full_name": "org/repo-b", "clone_url": "https://github.com/org/repo-b.git"},
        ],
        github_branches_cache={
            "org/repo-a": ["main", "feature-x"],
            "org/repo-b": ["develop"],
        },
        default_layout="horizontal",
        default_panes=3,
        cleanup_policy="persistent",
        tmux_auto_install=False,
        runtime_profile="wsl",
        wsl_distribution="Ubuntu",
        terminal_default_runtime="powershell",
        terminal_max_count=12,
        session_restore_enabled=False,
        last_session={
            "layout": "grid",
            "template_count": 2,
            "focused_terminal_id": "t1",
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
                    "branch": "feature",
                },
            ],
        },
    )
    save_config(original, path)
    loaded = load_config(path)
    assert loaded.default_root == "/repos"
    assert loaded.remote_repo_url == "https://github.com/org/repo.git"
    assert loaded.github_token == ""
    assert loaded.github_repositories_cache == [
        {"full_name": "org/repo-a", "clone_url": "https://github.com/org/repo-a.git"},
        {"full_name": "org/repo-b", "clone_url": "https://github.com/org/repo-b.git"},
    ]
    assert loaded.github_branches_cache == {
        "org/repo-a": ["main", "feature-x"],
        "org/repo-b": ["develop"],
    }
    assert loaded.default_layout == "horizontal"
    assert loaded.default_panes == 3
    assert loaded.cleanup_policy == "persistent"
    assert loaded.tmux_auto_install is False
    assert loaded.wsl_distribution == "Ubuntu"
    assert loaded.terminal_default_runtime == "powershell"
    assert loaded.terminal_max_count == 12
    assert loaded.session_restore_enabled is False
    assert loaded.last_session["template_count"] == 2
    assert len(loaded.last_session["terminals"]) == 2
    persisted = path.read_text(encoding="utf-8")
    assert "github_token" not in persisted


def test_env_github_token_overrides_config_file(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config.toml"
    path.write_text('github_token = "legacy_token"\n', encoding="utf-8")
    monkeypatch.setenv("BRANCHNEXUS_GH_TOKEN", "env_token")
    loaded = load_config(path)
    assert loaded.github_token == "env_token"


def test_corrupt_toml_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("not = [valid", encoding="utf-8")
    cfg = load_config(path)
    assert cfg.default_layout == "grid"
    assert cfg.wsl_distribution == ""


def test_set_wsl_distribution_updates_file(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    set_wsl_distribution("Debian", path)
    loaded = load_config(path)
    assert loaded.wsl_distribution == "Debian"


def test_invalid_runtime_fields_fall_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                'terminal_default_runtime = "cmd"',
                "terminal_max_count = 99",
                'last_session = "not-json"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded.terminal_default_runtime == "wsl"
    assert loaded.terminal_max_count == 16
    assert loaded.last_session == {}


def test_invalid_github_cache_fields_fall_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                'github_repositories_cache = "not-json"',
                'github_branches_cache = "{\"repo\":123}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded.github_repositories_cache == []
    assert loaded.github_branches_cache == {}


def test_legacy_runtime_fields_are_ignored_and_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                'ui_mode = "wizard"',
                "runtime_v2_enabled = false",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded.default_layout == "grid"

    save_config(loaded, path)
    persisted = path.read_text(encoding="utf-8")
    assert "ui_mode" not in persisted
    assert "runtime_v2_enabled" not in persisted
