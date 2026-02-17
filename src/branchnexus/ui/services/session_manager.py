"""Session and workspace reset helpers for runtime UI."""

from __future__ import annotations

import logging as py_logging
import os
import shlex
import shutil
import time
from contextlib import suppress
from pathlib import Path

from branchnexus.config import (
    DEFAULT_CLEANUP,
    DEFAULT_LAYOUT,
    DEFAULT_MAX_TERMINALS,
    DEFAULT_PANES,
    DEFAULT_RUNTIME_PROFILE,
    DEFAULT_TERMINAL_RUNTIME,
    AppConfig,
    save_config,
)
from branchnexus.errors import BranchNexusError
from branchnexus.git.remote_workspace import resolve_wsl_home_directory
from branchnexus.runtime.wsl_discovery import list_distributions, to_wsl_path
from branchnexus.ui.services.wsl_runner import run_wsl_probe_script

logger = py_logging.getLogger(__name__)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def select_runtime_wsl_distribution(
    available_distributions: list[str],
    *,
    configured: str = "",
    current: str = "",
) -> str:
    """Return a preferred WSL distribution from discovered values."""
    available = [item.strip() for item in available_distributions if item.strip()]
    if not available:
        return ""
    if current.strip() in set(available):
        return current.strip()
    if configured.strip() in set(available):
        return configured.strip()
    return available[0]


def _is_wsl_windows_mount_path(path: str) -> bool:
    value = path.strip()
    return value.startswith("/mnt/") and len(value) > 6 and value[5].isalpha() and value[6] == "/"


def _resolve_default_windows_workspace_root_wsl(distribution: str) -> str:
    host_candidates: list[str] = []
    user_profile = os.environ.get("USERPROFILE", "").strip()
    if user_profile:
        host_candidates.append(user_profile)
    home_drive = os.environ.get("HOMEDRIVE", "").strip()
    home_path = os.environ.get("HOMEPATH", "").strip()
    if home_drive and home_path:
        host_candidates.append(f"{home_drive}{home_path}")

    for host_path in _dedupe(host_candidates):
        try:
            converted = to_wsl_path(distribution, host_path)
        except (BranchNexusError, OSError):
            logger.debug("runtime-open windows-root conversion failed path=%s", host_path, exc_info=True)
            continue
        if converted.startswith("/mnt/"):
            return f"{converted.rstrip('/')}/branchnexus-workspace"
    return ""


def default_workspace_path() -> Path | None:
    """Return default host workspace path under USERPROFILE."""
    user_profile = os.environ.get("USERPROFILE", "").strip()
    if not user_profile:
        return None
    return Path(user_profile) / "branchnexus-workspace"


def remove_tree(
    path: Path,
    *,
    attempts: int = 3,
    delay_seconds: float = 0.25,
) -> OSError | None:
    """Remove directory tree with retries and linear backoff."""
    last_error: OSError | None = None
    for attempt in range(max(1, attempts)):
        try:
            if path.exists():
                shutil.rmtree(path)
            return None
        except OSError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(delay_seconds * (attempt + 1))
    return last_error


def is_safe_reset_path(path: str) -> bool:
    """Only allow runtime reset under dedicated workspace root."""
    root = path.strip().rstrip("/")
    return root.startswith("/") and root.endswith("/branchnexus-workspace")


def clear_fresh_start_config(config: AppConfig) -> None:
    """Reset persisted app config to fresh defaults."""
    config.default_root = ""
    config.remote_repo_url = ""
    config.github_token = ""
    config.github_repositories_cache = []
    config.github_branches_cache = {}
    config.default_layout = DEFAULT_LAYOUT
    config.default_panes = DEFAULT_PANES
    config.cleanup_policy = DEFAULT_CLEANUP
    config.tmux_auto_install = True
    config.runtime_profile = DEFAULT_RUNTIME_PROFILE
    config.wsl_distribution = ""
    config.terminal_default_runtime = DEFAULT_TERMINAL_RUNTIME
    config.terminal_max_count = DEFAULT_MAX_TERMINALS
    config.session_restore_enabled = True
    config.last_session = {}
    config.presets = {}
    config.command_hooks = {}


def resolve_fresh_distribution(configured_distribution: str) -> str:
    """Resolve best distribution to use during fresh-start cleanup."""
    configured = configured_distribution.strip()
    with suppress(BranchNexusError):
        available = list_distributions()
        return select_runtime_wsl_distribution(available, configured=configured)
    return configured


def resolve_wsl_workspace_root(distribution: str, configured_root: str) -> str:
    """Resolve WSL workspace root while forcing Linux-side location."""
    home = resolve_wsl_home_directory(distribution=distribution)
    home_default = str(home / "branchnexus-workspace")

    def _coerce_runtime_root(path_value: str, *, source: str) -> str:
        if not path_value.startswith("/"):
            return ""
        if _is_wsl_windows_mount_path(path_value):
            logger.info(
                "runtime-open workspace-root-forced-linux source=%s path=%s fallback=%s",
                source,
                path_value,
                home_default,
            )
            return home_default
        return path_value

    value = configured_root.strip()
    if value.startswith("/"):
        coerced = _coerce_runtime_root(value, source="configured")
        if coerced:
            return coerced
    if value:
        try:
            converted = to_wsl_path(distribution, value)
            coerced = _coerce_runtime_root(converted, source="configured-converted")
            if coerced:
                return coerced
        except (BranchNexusError, OSError):
            logger.debug("runtime-open workspace-root conversion failed root=%s", value, exc_info=True)
    logger.info("runtime-open workspace-root-default wsl-home=%s", home_default)
    return home_default


def reset_workspace(
    *,
    config: AppConfig,
    config_path: str | Path | None = None,
    wsl_distribution: str = "",
) -> list[str]:
    """Run fresh-start cleanup for both host and WSL workspace state."""
    warnings: list[str] = []
    selected_distribution = wsl_distribution.strip() or resolve_fresh_distribution(
        config.wsl_distribution,
    )
    workspace_root_wsl = ""
    if selected_distribution:
        with suppress(BranchNexusError, OSError):
            workspace_root_wsl = resolve_wsl_workspace_root(
                selected_distribution,
                config.default_root,
            )

    windows_workspace = default_workspace_path()
    windows_cleanup_error: OSError | None = None
    if windows_workspace:
        windows_cleanup_error = remove_tree(windows_workspace)

    if selected_distribution and is_safe_reset_path(workspace_root_wsl):
        try:
            run_wsl_probe_script(
                distribution=selected_distribution,
                script=f"rm -rf {shlex.quote(workspace_root_wsl)}",
                step="fresh-start:wsl-workspace",
            )
        except BranchNexusError as exc:
            warnings.append(f"WSL workspace silinemedi: {exc.message}")

    if windows_cleanup_error and windows_workspace:
        retry_error = remove_tree(windows_workspace, attempts=2, delay_seconds=0.5)
        if retry_error and windows_workspace.exists():
            warnings.append(f"Windows workspace silinemedi: {windows_cleanup_error}")
        else:
            logger.info("runtime-open fresh-start windows-workspace removed after fallback cleanup")

    clear_fresh_start_config(config)
    save_config(config, config_path)
    if warnings:
        logger.warning("runtime-open fresh-start warnings=%s", " | ".join(warnings))
    else:
        logger.info("runtime-open fresh-start completed")
    return warnings


# Backward compatibility aliases during app.py extraction.
_default_windows_workspace_path = default_workspace_path
_remove_tree_with_retries = remove_tree
_is_safe_workspace_root_for_reset = is_safe_reset_path
_clear_config_for_fresh_start = clear_fresh_start_config
_resolve_fresh_start_distribution = resolve_fresh_distribution
_run_fresh_start_reset = reset_workspace
_resolve_runtime_workspace_root_wsl = resolve_wsl_workspace_root
