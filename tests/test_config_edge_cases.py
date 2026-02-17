"""Config module edge case tests."""

from __future__ import annotations

from pathlib import Path

from branchnexus.config import AppConfig, load_config, save_config


def test_config_accepts_boundary_panes_values(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    cfg = AppConfig(default_panes=2)
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.default_panes == 2

    cfg = AppConfig(default_panes=6)
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.default_panes == 6


def test_config_accepts_boundary_terminal_max_count(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    cfg = AppConfig(terminal_max_count=2)
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.terminal_max_count == 2

    cfg = AppConfig(terminal_max_count=16)
    save_config(cfg, path)
    loaded = load_config(path)
    assert loaded.terminal_max_count == 16


def test_config_invalid_json_in_session_returns_empty(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('last_session = "not-json-{broken}"\n', encoding="utf-8")
    loaded = load_config(path)
    assert loaded.last_session == {}


def test_config_deduplicates_repository_cache(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'github_repositories_cache = "[{\\"full_name\\": \\"org/repo\\", \\"clone_url\\": \\"https://github.com/org/repo.git\\"},{\\"full_name\\": \\"org/repo\\", \\"clone_url\\": \\"https://github.com/org/repo.git\\"}]"\n',
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert len(loaded.github_repositories_cache) == 1


def test_config_trims_whitespace_in_cache(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'github_repositories_cache = "[{\\"full_name\\": \\" org/repo \\", \\"clone_url\\": \\" https://github.com/org/repo.git \\"}]"\n'
        + 'github_branches_cache = "{\\"org/repo\\": [\\" main \\", \\" feature \\"]}"\n',
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded.github_repositories_cache[0]["full_name"] == "org/repo"
    assert loaded.github_branches_cache == {"org/repo": ["main", "feature"]}


def test_config_empty_file_returns_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("", encoding="utf-8")
    loaded = load_config(path)
    assert loaded.default_layout == "grid"
    assert loaded.default_panes == 4
    assert loaded.cleanup_policy == "session"
