"""XDG config loading/saving."""

from __future__ import annotations

import json
import os
import sys
from contextlib import suppress
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing_extensions import TypedDict

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from branchnexus.session import parse_runtime_snapshot

DEFAULT_CONFIG_PATH = Path("~/.config/branchnexus/config.toml").expanduser()
DEFAULT_LAYOUT: Literal["horizontal", "vertical", "grid"] = "grid"
DEFAULT_PANES = 4
DEFAULT_CLEANUP: Literal["session", "persistent"] = "session"
DEFAULT_RUNTIME_PROFILE: Literal["wsl"] = "wsl"
DEFAULT_TERMINAL_RUNTIME: Literal["wsl", "powershell"] = "wsl"
DEFAULT_MAX_TERMINALS = 16
GITHUB_TOKEN_ENV = "BRANCHNEXUS_GH_TOKEN"

_VALID_LAYOUTS = {"horizontal", "vertical", "grid"}
_VALID_CLEANUP = {"session", "persistent"}
_VALID_TERMINAL_RUNTIMES = {"wsl", "powershell"}


class RepositoryCacheEntry(TypedDict):
    full_name: str
    clone_url: str


class PresetConfig(TypedDict):
    layout: str
    panes: int
    cleanup: str


class AppConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    default_root: str = ""
    remote_repo_url: str = ""
    github_token: str = ""
    github_repositories_cache: list[RepositoryCacheEntry] = Field(default_factory=list)
    github_branches_cache: dict[str, list[str]] = Field(default_factory=dict)
    default_layout: Literal["horizontal", "vertical", "grid"] = DEFAULT_LAYOUT
    default_panes: int = Field(default=DEFAULT_PANES, ge=2, le=6)
    cleanup_policy: Literal["session", "persistent"] = DEFAULT_CLEANUP
    tmux_auto_install: bool = True
    runtime_profile: str = DEFAULT_RUNTIME_PROFILE
    wsl_distribution: str = ""
    terminal_default_runtime: Literal["wsl", "powershell"] = DEFAULT_TERMINAL_RUNTIME
    terminal_max_count: int = Field(default=DEFAULT_MAX_TERMINALS, ge=2, le=16)
    session_restore_enabled: bool = True
    last_session: dict[str, object] = Field(default_factory=dict)
    presets: dict[str, PresetConfig] = Field(default_factory=dict)
    command_hooks: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("default_layout")
    @classmethod
    def _validate_layout(cls, value: str) -> str:
        if value not in _VALID_LAYOUTS:
            raise ValueError(f"Invalid layout: {value}")
        return value

    @field_validator("cleanup_policy")
    @classmethod
    def _validate_cleanup(cls, value: str) -> str:
        if value not in _VALID_CLEANUP:
            raise ValueError(f"Invalid cleanup policy: {value}")
        return value

    @field_validator("terminal_default_runtime")
    @classmethod
    def _validate_runtime(cls, value: str) -> str:
        if value not in _VALID_TERMINAL_RUNTIMES:
            raise ValueError(f"Invalid terminal runtime: {value}")
        return value


def get_config_path(path: str | Path | None = None) -> Path:
    if path is None:
        return DEFAULT_CONFIG_PATH
    return Path(path).expanduser()


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _toml_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return f'"{_escape(value)}"'
    if isinstance(value, list):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    raise TypeError(f"Unsupported TOML scalar type: {type(value)!r}")


def _decode_json_container(value: object) -> object | None:
    if isinstance(value, str):
        try:
            loaded: object = json.loads(value)
            return loaded
        except json.JSONDecodeError:
            return None
    return value


def _normalize_repo_cache(value: object) -> list[RepositoryCacheEntry]:
    entries = _decode_json_container(value)
    if not isinstance(entries, list):
        return []

    normalized: list[RepositoryCacheEntry] = []
    seen_names: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        full_name = item.get("full_name")
        clone_url = item.get("clone_url")
        if not isinstance(full_name, str) or not isinstance(clone_url, str):
            continue
        repo_name = full_name.strip()
        repo_url = clone_url.strip()
        if not repo_name or not repo_url or repo_name in seen_names:
            continue
        seen_names.add(repo_name)
        normalized.append(RepositoryCacheEntry(full_name=repo_name, clone_url=repo_url))
    return normalized


def _normalize_branches_cache(value: object) -> dict[str, list[str]]:
    raw_cache = _decode_json_container(value)
    if not isinstance(raw_cache, dict):
        return {}

    normalized: dict[str, list[str]] = {}
    for repo_name, branches in raw_cache.items():
        if not isinstance(repo_name, str) or not isinstance(branches, list):
            continue
        key = repo_name.strip()
        if not key:
            continue
        branch_list: list[str] = []
        seen_branches: set[str] = set()
        for branch in branches:
            if not isinstance(branch, str):
                continue
            branch_name = branch.strip()
            if not branch_name or branch_name in seen_branches:
                continue
            seen_branches.add(branch_name)
            branch_list.append(branch_name)
        normalized[key] = branch_list
    return normalized


def _normalize_presets(value: object, defaults: AppConfig) -> dict[str, PresetConfig]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, PresetConfig] = {}
    for name, payload in value.items():
        if not isinstance(name, str) or not isinstance(payload, dict):
            continue
        layout_value = payload.get("layout", defaults.default_layout)
        panes_value = payload.get("panes", defaults.default_panes)
        cleanup_value = payload.get("cleanup", defaults.cleanup_policy)
        layout = (
            layout_value
            if isinstance(layout_value, str) and layout_value in _VALID_LAYOUTS
            else defaults.default_layout
        )
        panes = (
            panes_value
            if isinstance(panes_value, int) and 2 <= panes_value <= 6
            else defaults.default_panes
        )
        cleanup = (
            cleanup_value
            if isinstance(cleanup_value, str) and cleanup_value in _VALID_CLEANUP
            else defaults.cleanup_policy
        )
        normalized[name] = PresetConfig(layout=layout, panes=panes, cleanup=cleanup)
    return normalized


def _normalize_command_hooks(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    normalized_hooks: dict[str, list[str]] = {}
    for pane_name, commands in value.items():
        if not isinstance(pane_name, str) or not isinstance(commands, list):
            continue
        normalized_hooks[pane_name] = [item for item in commands if isinstance(item, str)]
    return normalized_hooks


def _sanitize(raw: dict[str, object]) -> AppConfig:
    cfg = AppConfig()

    default_root = raw.get("default_root", cfg.default_root)
    if isinstance(default_root, str):
        cfg.default_root = default_root

    remote_repo_url = raw.get("remote_repo_url", cfg.remote_repo_url)
    if isinstance(remote_repo_url, str):
        cfg.remote_repo_url = remote_repo_url

    github_token = raw.get("github_token", cfg.github_token)
    if isinstance(github_token, str):
        cfg.github_token = github_token
    env_token = os.getenv(GITHUB_TOKEN_ENV, "").strip()
    if env_token:
        cfg.github_token = env_token

    cfg.github_repositories_cache = _normalize_repo_cache(raw.get("github_repositories_cache", []))
    cfg.github_branches_cache = _normalize_branches_cache(raw.get("github_branches_cache", {}))

    default_layout = raw.get("default_layout", cfg.default_layout)
    if isinstance(default_layout, str) and default_layout in _VALID_LAYOUTS:
        cfg.default_layout = cast(Literal["horizontal", "vertical", "grid"], default_layout)

    default_panes = raw.get("default_panes", cfg.default_panes)
    if isinstance(default_panes, int) and 2 <= default_panes <= 6:
        cfg.default_panes = default_panes

    cleanup_policy = raw.get("cleanup_policy", cfg.cleanup_policy)
    if isinstance(cleanup_policy, str) and cleanup_policy in _VALID_CLEANUP:
        cfg.cleanup_policy = cast(Literal["session", "persistent"], cleanup_policy)

    tmux_auto_install = raw.get("tmux_auto_install", cfg.tmux_auto_install)
    if isinstance(tmux_auto_install, bool):
        cfg.tmux_auto_install = tmux_auto_install

    runtime_profile = raw.get("runtime_profile", cfg.runtime_profile)
    if isinstance(runtime_profile, str) and runtime_profile == "wsl":
        cfg.runtime_profile = runtime_profile

    wsl_distribution = raw.get("wsl_distribution", "")
    if isinstance(wsl_distribution, str):
        cfg.wsl_distribution = wsl_distribution

    terminal_default_runtime = raw.get("terminal_default_runtime", cfg.terminal_default_runtime)
    if (
        isinstance(terminal_default_runtime, str)
        and terminal_default_runtime in _VALID_TERMINAL_RUNTIMES
    ):
        cfg.terminal_default_runtime = cast(
            Literal["wsl", "powershell"],
            terminal_default_runtime,
        )

    terminal_max_count = raw.get("terminal_max_count", cfg.terminal_max_count)
    if isinstance(terminal_max_count, int) and 2 <= terminal_max_count <= 16:
        cfg.terminal_max_count = terminal_max_count

    session_restore_enabled = raw.get("session_restore_enabled", cfg.session_restore_enabled)
    if isinstance(session_restore_enabled, bool):
        cfg.session_restore_enabled = session_restore_enabled

    last_session_raw = raw.get("last_session", cfg.last_session)
    decoded_session: dict[str, object] | None = None
    if isinstance(last_session_raw, dict):
        decoded_session = cast(dict[str, object], last_session_raw)
    elif isinstance(last_session_raw, str):
        try:
            decoded = json.loads(last_session_raw)
        except json.JSONDecodeError:
            decoded = {}
        if isinstance(decoded, dict):
            decoded_session = cast(dict[str, object], decoded)

    parsed_session = parse_runtime_snapshot(decoded_session)
    if parsed_session is not None:
        cfg.last_session = parsed_session.to_dict()
    else:
        cfg.last_session = {}

    cfg.presets = _normalize_presets(raw.get("presets", {}), cfg)
    cfg.command_hooks = _normalize_command_hooks(raw.get("command_hooks", {}))

    return cfg


def load_config(path: str | Path | None = None) -> AppConfig:
    resolved = get_config_path(path)
    if not resolved.exists():
        return AppConfig()
    try:
        with resolved.open("rb") as handle:
            raw = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError):
        return AppConfig()
    if not isinstance(raw, dict):
        return AppConfig()
    return _sanitize(raw)


def save_config(config: AppConfig, path: str | Path | None = None) -> Path:
    resolved = get_config_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    repo_cache = _normalize_repo_cache(config.github_repositories_cache)
    branches_cache = _normalize_branches_cache(config.github_branches_cache)

    lines = [
        f"default_root = {_toml_scalar(config.default_root)}",
        f"remote_repo_url = {_toml_scalar(config.remote_repo_url)}",
        f"github_repositories_cache = {_toml_scalar(json.dumps(repo_cache, ensure_ascii=True, separators=(',', ':')))}",
        f"github_branches_cache = {_toml_scalar(json.dumps(branches_cache, ensure_ascii=True, separators=(',', ':')))}",
        f"default_layout = {_toml_scalar(config.default_layout)}",
        f"default_panes = {_toml_scalar(config.default_panes)}",
        f"cleanup_policy = {_toml_scalar(config.cleanup_policy)}",
        f"tmux_auto_install = {_toml_scalar(config.tmux_auto_install)}",
        f"runtime_profile = {_toml_scalar(config.runtime_profile)}",
        f"wsl_distribution = {_toml_scalar(config.wsl_distribution)}",
        f"terminal_default_runtime = {_toml_scalar(config.terminal_default_runtime)}",
        f"terminal_max_count = {_toml_scalar(config.terminal_max_count)}",
        f"session_restore_enabled = {_toml_scalar(config.session_restore_enabled)}",
        f"last_session = {_toml_scalar(json.dumps(dict(config.last_session), ensure_ascii=True, separators=(',', ':')))}",
    ]

    for name, payload in sorted(config.presets.items()):
        lines.extend(
            [
                "",
                f'[presets."{_escape(name)}"]',
                f"layout = {_toml_scalar(str(payload.get('layout', DEFAULT_LAYOUT)))}",
                f"panes = {_toml_scalar(int(payload.get('panes', DEFAULT_PANES)))}",
                f"cleanup = {_toml_scalar(str(payload.get('cleanup', DEFAULT_CLEANUP)))}",
            ]
        )

    if config.command_hooks:
        lines.append("")
        lines.append("[command_hooks]")
        for pane_name, commands in sorted(config.command_hooks.items()):
            lines.append(f'"{_escape(pane_name)}" = {_toml_scalar(commands)}')

    resolved.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with suppress(OSError):
        resolved.chmod(0o600)
    return resolved


def set_wsl_distribution(distribution: str, path: str | Path | None = None) -> AppConfig:
    config = load_config(path)
    config.wsl_distribution = distribution
    save_config(config, path)
    return config
