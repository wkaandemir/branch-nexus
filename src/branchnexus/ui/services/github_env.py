"""Shared helpers for GitHub token environment variables."""

from __future__ import annotations

GITHUB_TOKEN_KEYS = ("BRANCHNEXUS_GH_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


def github_token_env(token: str) -> dict[str, str]:
    """Return a dict with the three GitHub token env vars set to the given token."""
    value = (token or "").strip()
    return {
        "BRANCHNEXUS_GH_TOKEN": value,
        "GH_TOKEN": value,
        "GITHUB_TOKEN": value,
    }


def github_token_tmux_env_script() -> str:
    """Return the bash snippet that sets or unsets GitHub token in tmux global env.

    To be run inside WSL where BRANCHNEXUS_GH_TOKEN may already be set.
    """
    return (
        'if [ -n "${BRANCHNEXUS_GH_TOKEN:-}" ]; then '
        'tmux set-environment -g BRANCHNEXUS_GH_TOKEN "${BRANCHNEXUS_GH_TOKEN}"; '
        'tmux set-environment -g GH_TOKEN "${BRANCHNEXUS_GH_TOKEN}"; '
        'tmux set-environment -g GITHUB_TOKEN "${BRANCHNEXUS_GH_TOKEN}"; '
        "else tmux set-environment -gu BRANCHNEXUS_GH_TOKEN; "
        "tmux set-environment -gu GH_TOKEN; "
        "tmux set-environment -gu GITHUB_TOKEN; fi"
    )


def env_without_github_token(env: dict[str, str]) -> dict[str, str]:
    """Return a copy of env with the three GitHub token keys removed."""
    out = dict(env)
    for key in GITHUB_TOKEN_KEYS:
        out.pop(key, None)
    return out
