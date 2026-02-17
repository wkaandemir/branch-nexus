"""Windows Terminal settings helpers for runtime launch."""

from __future__ import annotations

import json
import logging as py_logging
import os
from pathlib import Path

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


def strip_jsonc_comments(raw: str) -> str:
    """Remove // and /* */ comments while preserving JSON strings."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    text_length = len(raw)
    while index < text_length:
        char = raw[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == "/" and index + 1 < text_length and raw[index + 1] == "/":
            index += 2
            while index < text_length and raw[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and index + 1 < text_length and raw[index + 1] == "*":
            index += 2
            while index + 1 < text_length:
                if raw[index] == "*" and raw[index + 1] == "/":
                    index += 2
                    break
                index += 1
            continue
        output.append(char)
        index += 1
    return "".join(output)


def fix_json_trailing_commas(raw: str) -> str:
    """Remove trailing commas before object/array terminators."""
    output: list[str] = []
    index = 0
    in_string = False
    escaped = False
    text_length = len(raw)
    while index < text_length:
        char = raw[index]
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            output.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < text_length and raw[lookahead] in " \t\r\n":
                lookahead += 1
            if lookahead < text_length and raw[lookahead] in "}]":
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output)


def get_settings_paths(environ: dict[str, str] | None = None) -> list[str]:
    """Return candidate Windows Terminal settings file paths."""
    env = environ or os.environ
    local_app_data = env.get("LOCALAPPDATA", "").strip()
    if not local_app_data:
        return []
    base = Path(local_app_data)
    return _dedupe(
        [
            str(
                base
                / "Packages"
                / "Microsoft.WindowsTerminal_8wekyb3d8bbwe"
                / "LocalState"
                / "settings.json"
            ),
            str(
                base
                / "Packages"
                / "Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe"
                / "LocalState"
                / "settings.json"
            ),
            str(base / "Microsoft" / "Windows Terminal" / "settings.json"),
        ]
    )


def profile_matches(profile: dict[str, object], distribution: str) -> bool:
    """Check if a terminal profile belongs to the selected WSL distro."""
    target = distribution.strip().lower()
    if not target:
        return False
    name = str(profile.get("name", "")).strip().lower()
    if name == target:
        return True
    commandline = str(profile.get("commandline", "")).strip().lower()
    if not commandline:
        return False
    return f"-d {target}" in commandline


def apply_font_size(
    *,
    distribution: str,
    font_size: int,
    environ: dict[str, str] | None = None,
    settings_paths: list[str] | None = None,
    platform_name: str | None = None,
) -> tuple[bool, str]:
    """Apply terminal font size for profile matching distribution."""
    runtime_platform = (platform_name or os.name).strip().lower()
    if runtime_platform != "nt":
        return False, "not-windows"
    target_distribution = distribution.strip()
    if not target_distribution:
        return False, "distribution-empty"
    target_size = max(8, min(24, int(font_size)))
    candidates = settings_paths or get_settings_paths(environ)
    if not candidates:
        return False, "settings-path-missing"

    for raw_path in candidates:
        path = Path(raw_path)
        if not path.exists():
            continue
        try:
            raw = path.read_text(encoding="utf-8-sig")
        except OSError:
            logger.debug("runtime-open wt-settings-read-failed path=%s", path, exc_info=True)
            continue
        try:
            cleaned = fix_json_trailing_commas(strip_jsonc_comments(raw))
            payload = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("runtime-open wt-settings-parse-failed path=%s", path)
            continue
        if not isinstance(payload, dict):
            continue

        profiles = payload.get("profiles")
        profile_list: list[dict[str, object]] = []
        if isinstance(profiles, dict):
            raw_list = profiles.get("list")
            if isinstance(raw_list, list):
                profile_list = [item for item in raw_list if isinstance(item, dict)]
        elif isinstance(profiles, list):
            profile_list = [item for item in profiles if isinstance(item, dict)]
        if not profile_list:
            continue

        selected_profile: dict[str, object] | None = None
        for profile in profile_list:
            if profile_matches(profile, target_distribution):
                selected_profile = profile
                break
        if selected_profile is None:
            continue

        selected_profile["fontSize"] = target_size
        font_payload = selected_profile.get("font")
        if isinstance(font_payload, dict):
            font_payload["size"] = target_size
        else:
            selected_profile["font"] = {"size": target_size}

        try:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=4) + "\n",
                encoding="utf-8",
            )
        except OSError:
            logger.debug("runtime-open wt-settings-write-failed path=%s", path, exc_info=True)
            continue
        logger.info(
            "runtime-open wt-font-size-applied distribution=%s size=%s path=%s",
            target_distribution,
            target_size,
            path,
        )
        return True, str(path)

    return False, "profile-not-found"


# Backward compatibility aliases during app.py extraction.
_strip_jsonc_comments = strip_jsonc_comments
_remove_json_trailing_commas = fix_json_trailing_commas
_windows_terminal_settings_paths = get_settings_paths
_profile_matches_distribution = profile_matches
_apply_windows_terminal_profile_font_size = apply_font_size
