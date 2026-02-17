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
    """Return the interactive install command (with plain sudo) for the given OS."""
    lowered = os_release.lower()

    # Debian family (apt-get)
    _debian_ids = ("debian", "ubuntu", "pengwin", "kali", "mint", "pop", "elementary", "zorin")
    if any(name in lowered for name in _debian_ids) or "id_like=debian" in lowered.replace(" ", ""):
        return "sudo apt-get update && sudo apt-get install -y tmux"

    # Red Hat family (dnf)
    _rhel_ids = ("fedora", "rhel", "centos", "rocky", "almalinux", "oracle", "amazon", "noble")
    if any(name in lowered for name in _rhel_ids):
        return "sudo dnf install -y tmux"

    # Arch family (pacman)
    _arch_ids = ("arch", "manjaro", "endeavouros", "garuda")
    if any(name in lowered for name in _arch_ids) or "id_like=arch" in lowered.replace(" ", ""):
        return "sudo pacman -S --noconfirm tmux"

    # SUSE family (zypper)
    if "opensuse" in lowered or "suse" in lowered:
        return "sudo zypper install -y tmux"

    # Alpine (apk)
    if "alpine" in lowered:
        return "sudo apk add tmux"

    # Void Linux (xbps)
    if "void" in lowered:
        return "sudo xbps-install -Sy tmux"

    # Gentoo (emerge)
    if "gentoo" in lowered:
        return "sudo emerge app-misc/tmux"

    # NixOS (nix profile — no sudo needed)
    if "nixos" in lowered or "nix" in lowered:
        return "nix profile install nixpkgs#tmux"

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


def _try_noninteractive_install(
    distribution: str,
    install_cmd: str,
    runner: callable,
) -> bool:
    """Attempt installation with sudo -n (no password prompt).

    Returns True if installation succeeded without a password.
    """
    noninteractive_cmd = install_cmd.replace("sudo ", "sudo -n ")
    logger.debug("Trying non-interactive tmux install in distribution=%s", distribution)
    result = runner(
        build_wsl_command(distribution, ["bash", "-lc", noninteractive_cmd]),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        logger.info("Non-interactive tmux install succeeded in distribution=%s", distribution)
        return True
    logger.debug(
        "Non-interactive install failed (password likely required) distribution=%s stderr=%s",
        distribution,
        result.stderr.strip()[:200],
    )
    return False


def _run_interactive_install(
    distribution: str,
    install_cmd: str,
) -> bool:
    """Open a visible WSL console for the user to enter their sudo password.

    The window stays open until the install finishes, then closes automatically.
    Returns True if the process exited successfully.
    """
    script = (
        f"echo '[BranchNexus] tmux kurulumu gerekli. Lutfen sudo sifrenizi girin:' && "
        f"{install_cmd} && "
        f"echo '' && echo '[BranchNexus] tmux basariyla kuruldu!' && sleep 1"
    )
    command = ["wsl.exe", "-d", distribution, "--", "bash", "-lc", script]
    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    logger.info(
        "Opening interactive WSL terminal for tmux install distribution=%s",
        distribution,
    )
    try:
        process = subprocess.Popen(command, creationflags=creation_flags)
        exit_code = process.wait()
        logger.info(
            "Interactive tmux install exited code=%s distribution=%s",
            exit_code,
            distribution,
        )
        return exit_code == 0
    except OSError:
        logger.error(
            "Failed to open interactive WSL terminal for tmux install",
            exc_info=True,
        )
        return False


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

    # 1) Try passwordless install first (fast path).
    if _try_noninteractive_install(distribution, install_cmd, runner):
        return BootstrapResult(tmux_available=True, install_attempted=True)

    # 2) Password required — open an interactive terminal for the user.
    logger.info("Passwordless sudo unavailable; opening interactive install window")
    if not _run_interactive_install(distribution, install_cmd):
        raise BranchNexusError(
            "Interactive tmux installation failed or was cancelled.",
            code=ExitCode.TMUX_ERROR,
            hint=_manual_install_guidance(os_release),
        )

    # 3) Verify tmux is actually installed after interactive step.
    verify = runner(
        build_wsl_command(distribution, ["command", "-v", "tmux"]),
        capture_output=True,
        text=True,
        check=False,
    )
    if verify.returncode != 0:
        logger.error("tmux still not found after interactive install distribution=%s", distribution)
        raise BranchNexusError(
            "tmux installation could not be verified.",
            code=ExitCode.TMUX_ERROR,
            hint=_manual_install_guidance(os_release),
        )

    logger.info("Automatic tmux installation succeeded in distribution=%s", distribution)
    return BootstrapResult(tmux_available=True, install_attempted=True)
