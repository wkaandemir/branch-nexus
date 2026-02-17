"""Tmux runtime bootstrap for selected WSL distribution."""

from __future__ import annotations

import logging as py_logging
import subprocess
from dataclasses import dataclass

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.runtime.wsl_discovery import build_wsl_command

logger = py_logging.getLogger(__name__)


@dataclass
class BootstrapResult:
    tmux_available: bool
    install_attempted: bool = False


def _install_command_for_os_release(os_release: str) -> str:
    lowered = os_release.lower()
    if "debian" in lowered or "ubuntu" in lowered:
        return "sudo apt-get update && sudo apt-get install -y tmux"
    if "fedora" in lowered or "rhel" in lowered or "centos" in lowered:
        return "sudo dnf install -y tmux"
    if "arch" in lowered:
        return "sudo pacman -S --noconfirm tmux"
    if "opensuse" in lowered or "suse" in lowered:
        return "sudo zypper install -y tmux"
    raise BranchNexusError(
        "Unsupported distribution for automatic tmux install.",
        code=ExitCode.TMUX_ERROR,
        hint="Install tmux manually inside the selected distribution.",
    )


def _manual_install_guidance(os_release: str) -> str:
    try:
        cmd = _install_command_for_os_release(os_release)
        return f"Run this inside WSL: {cmd}"
    except BranchNexusError:
        return "Install tmux manually in the selected distribution and retry."


def ensure_tmux(
    distribution: str,
    *,
    auto_install: bool,
    runner: callable = subprocess.run,
) -> BootstrapResult:
    logger.debug("Checking tmux availability in distribution=%s", distribution)
    check = runner(
        build_wsl_command(distribution, ["command", "-v", "tmux"]),
        capture_output=True,
        text=True,
        check=False,
    )
    if check.returncode == 0:
        logger.debug("tmux is already installed in distribution=%s", distribution)
        return BootstrapResult(tmux_available=True, install_attempted=False)

    os_release_result = runner(
        build_wsl_command(distribution, ["cat", "/etc/os-release"]),
        capture_output=True,
        text=True,
        check=False,
    )
    os_release = os_release_result.stdout if os_release_result.returncode == 0 else ""
    logger.warning("tmux not found in distribution=%s auto_install=%s", distribution, auto_install)

    if not auto_install:
        logger.error("tmux missing and auto-install disabled in distribution=%s", distribution)
        raise BranchNexusError(
            "tmux is not installed in selected WSL distribution.",
            code=ExitCode.TMUX_ERROR,
            hint=_manual_install_guidance(os_release),
        )

    install_cmd = _install_command_for_os_release(os_release)
    logger.info("Attempting automatic tmux installation in distribution=%s", distribution)
    install_result = runner(
        build_wsl_command(distribution, ["bash", "-lc", install_cmd]),
        capture_output=True,
        text=True,
        check=False,
    )
    if install_result.returncode != 0:
        logger.error(
            "Automatic tmux installation failed in distribution=%s stderr=%s",
            distribution,
            install_result.stderr.strip(),
        )
        raise BranchNexusError(
            "Automatic tmux installation failed.",
            code=ExitCode.TMUX_ERROR,
            hint=_manual_install_guidance(os_release),
        )

    logger.info("Automatic tmux installation succeeded in distribution=%s", distribution)
    return BootstrapResult(tmux_available=True, install_attempted=True)
