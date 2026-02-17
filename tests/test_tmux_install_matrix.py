from __future__ import annotations

import subprocess

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.tmux.bootstrap import ensure_tmux


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.mark.parametrize(
    ("os_release", "expected_noninteractive_install"),
    [
        # Debian family (sudo -n added by _try_noninteractive_install)
        ("ID=ubuntu", "sudo -n apt-get update && sudo -n apt-get install -y tmux"),
        ("ID=debian", "sudo -n apt-get update && sudo -n apt-get install -y tmux"),
        ("NAME=\"Pengwin\"\nID_LIKE=debian", "sudo -n apt-get update && sudo -n apt-get install -y tmux"),
        ("ID=kali", "sudo -n apt-get update && sudo -n apt-get install -y tmux"),
        ("ID=linuxmint\nID_LIKE=debian", "sudo -n apt-get update && sudo -n apt-get install -y tmux"),
        # Red Hat family
        ("ID=fedora", "sudo -n dnf install -y tmux"),
        ("ID=rocky", "sudo -n dnf install -y tmux"),
        ("ID=almalinux", "sudo -n dnf install -y tmux"),
        # Arch family
        ("ID=arch", "sudo -n pacman -S --noconfirm tmux"),
        ("ID=manjaro\nID_LIKE=arch", "sudo -n pacman -S --noconfirm tmux"),
        # SUSE family
        ("ID=opensuse", "sudo -n zypper install -y tmux"),
        # Alpine
        ("ID=alpine", "sudo -n apk add tmux"),
        # Void
        ("ID=void", "sudo -n xbps-install -Sy tmux"),
        # Gentoo
        ("ID=gentoo", "sudo -n emerge app-misc/tmux"),
        # NixOS (no sudo)
        ("ID=nixos", "nix profile install nixpkgs#tmux"),
    ],
)
def test_install_command_matrix(os_release: str, expected_noninteractive_install: str) -> None:
    install_seen = {"cmd": ""}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(1)
        if cmd[-2:] == ["cat", "/etc/os-release"]:
            return _cp(0, os_release)
        if cmd[-3:] == ["bash", "-lc", expected_noninteractive_install]:
            install_seen["cmd"] = cmd[-1]
            return _cp(0)
        raise AssertionError(f"unexpected command: {cmd}")

    result = ensure_tmux("Any", auto_install=True, runner=runner)
    assert result.install_attempted is True
    assert install_seen["cmd"] == expected_noninteractive_install


def test_unknown_distro_returns_fallback_message_snapshot() -> None:
    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(1)
        if cmd[-2:] == ["cat", "/etc/os-release"]:
            return _cp(0, "ID=unknown")
        return _cp(1)

    with pytest.raises(BranchNexusError) as exc:
        ensure_tmux("Any", auto_install=False, runner=runner)
    assert str(exc.value) == (
        "tmux is not installed in selected WSL distribution. "
        "Hint: Install tmux manually in the selected distribution and retry."
    )
