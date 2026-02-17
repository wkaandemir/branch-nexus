from __future__ import annotations

import branchnexus.ui.services.git_operations as git_ops
import branchnexus.ui.services.security as security


def test_build_git_env_injects_header_without_command_mutation() -> None:
    env = git_ops.build_git_env({"PATH": "/usr/bin"}, token="ghp_secret")
    assert env["PATH"] == "/usr/bin"
    assert env["GIT_CONFIG_COUNT"] == "1"
    assert env["GIT_CONFIG_KEY_0"] == "http.extraheader"
    assert env["GIT_CONFIG_VALUE_0"] == "Authorization: Bearer ghp_secret"


def test_build_git_env_appends_existing_git_config_entries() -> None:
    env = git_ops.build_git_env(
        {
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "user.name",
            "GIT_CONFIG_VALUE_0": "BranchNexus",
        },
        token="ghp_secret",
    )
    assert env["GIT_CONFIG_COUNT"] == "2"
    assert env["GIT_CONFIG_KEY_1"] == "http.extraheader"
    assert env["GIT_CONFIG_VALUE_1"] == "Authorization: Bearer ghp_secret"


def test_sanitize_terminal_log_text_masks_secrets() -> None:
    value = (
        "Authorization: Bearer ghp_123456 https://user:pass@github.com/org/repo.git "
        "token=gho_ABCDEF123"
    )
    sanitized = security.sanitize_terminal_log_text(value)
    assert "Bearer ***" in sanitized
    assert "https://***:***@github.com/org/repo.git" in sanitized
    assert "ghp_123456" not in sanitized
    assert "gho_ABCDEF123" not in sanitized


def test_command_for_log_truncates_safely() -> None:
    payload = ["git", "clone", "https://github.com/org/repo.git", "x" * 800]
    rendered = security.command_for_log(payload)
    assert rendered.startswith("git clone ")
    assert len(rendered) <= security.DEFAULT_LOG_TRUNCATE_LIMIT
