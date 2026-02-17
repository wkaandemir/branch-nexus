"""WSL distribution discovery and command builders."""

from __future__ import annotations

import logging as py_logging
import re
import subprocess
from collections.abc import Sequence

from branchnexus.errors import BranchNexusError, ExitCode

logger = py_logging.getLogger(__name__)


def _decode_process_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if not value:
        return ""

    # wsl.exe may emit UTF-16LE in Windows consoles.
    if b"\x00" in value:
        for encoding in ("utf-16le", "utf-16"):
            try:
                return value.decode(encoding).replace("\ufeff", "")
            except UnicodeDecodeError:
                continue

    for encoding in ("utf-8", "cp1254", "cp1252"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


_WINDOWS_DRIVE_PATH = re.compile(r"^(?P<drive>[A-Za-z]):[\\/](?P<rest>.*)$")


def _normalize_host_path_for_wslpath(host_path: str) -> str:
    return host_path.replace("\\", "/")


def _fallback_windows_to_wsl_path(host_path: str) -> str:
    match = _WINDOWS_DRIVE_PATH.match(host_path)
    if not match:
        return ""
    drive = match.group("drive").lower()
    rest = match.group("rest").replace("\\", "/").strip("/")
    if not rest:
        return f"/mnt/{drive}"
    return f"/mnt/{drive}/{rest}"


def list_distributions(runner: callable = subprocess.run) -> list[str]:
    logger.debug("Listing WSL distributions using wsl.exe -l -q")
    result = runner(["wsl.exe", "-l", "-q"], capture_output=True, text=False, check=False)
    stdout = _decode_process_output(result.stdout)
    stderr = _decode_process_output(result.stderr)
    if result.returncode != 0:
        logger.error("WSL distribution listing failed: %s", stderr.strip())
        raise BranchNexusError(
            "Failed to list WSL distributions.",
            code=ExitCode.RUNTIME_ERROR,
            hint=(stderr or "Check WSL installation.").strip(),
        )

    distros = sorted({line.strip() for line in stdout.splitlines() if line.strip()})
    if not distros:
        logger.error("No WSL distributions discovered")
        raise BranchNexusError(
            "No WSL distributions were found.",
            code=ExitCode.RUNTIME_ERROR,
            hint="Install a distribution using `wsl --install` and retry.",
        )
    logger.debug("Discovered %s WSL distributions", len(distros))
    return distros


def validate_distribution(distribution: str, available: Sequence[str]) -> bool:
    return distribution in set(available)


def build_wsl_command(distribution: str, command: Sequence[str]) -> list[str]:
    if not distribution:
        logger.error("WSL command requested without distribution")
        raise BranchNexusError(
            "WSL distribution is required.",
            code=ExitCode.VALIDATION_ERROR,
            hint="Select a distribution before orchestration.",
        )
    if not command:
        logger.error("WSL command requested with empty payload")
        raise BranchNexusError(
            "Runtime command is empty.",
            code=ExitCode.VALIDATION_ERROR,
            hint="Provide a command to execute in WSL.",
        )
    return ["wsl.exe", "-d", distribution, "--", *command]


def to_wsl_path(
    distribution: str,
    host_path: str,
    *,
    runner: callable = subprocess.run,
) -> str:
    normalized = _normalize_host_path_for_wslpath(host_path)
    if normalized.startswith("/") and not normalized.startswith("//"):
        return normalized

    command = build_wsl_command(distribution, ["wslpath", "-a", normalized])
    logger.debug("Resolving WSL path for host path: %s", host_path)
    result = runner(command, capture_output=True, text=False, check=False)
    stdout = _decode_process_output(result.stdout).strip()
    stderr = _decode_process_output(result.stderr).strip()
    if result.returncode != 0 or not stdout:
        fallback = _fallback_windows_to_wsl_path(normalized)
        if fallback:
            logger.warning("wslpath failed, using fallback mapping for host path: %s", host_path)
            return fallback
        logger.error("Failed to convert host path to WSL path: %s", host_path)
        raise BranchNexusError(
            f"Failed to convert host path to WSL path: {host_path}",
            code=ExitCode.RUNTIME_ERROR,
            hint=stderr or "Ensure selected WSL distribution is running.",
        )
    return stdout


def distribution_unreachable_message(distribution: str) -> str:
    return (
        f"Selected WSL distribution '{distribution}' is not reachable. "
        "Choose another distribution or start this one manually and retry."
    )
