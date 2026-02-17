from __future__ import annotations

import subprocess

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.tmux.bootstrap import ensure_tmux


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


@pytest.mark.parametrize(
    ("os_release", "expected_install"),
    [
        ("ID=ubuntu", "sudo apt-get update && sudo apt-get install -y tmux"),
        ("ID=fedora", "sudo dnf install -y tmux"),
        ("ID=arch", "sudo pacman -S --noconfirm tmux"),
        ("ID=opensuse", "sudo zypper install -y tmux"),
    ],
)
def test_install_command_matrix(os_release: str, expected_install: str) -> None:
    install_seen = {"cmd": ""}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(1)
        if cmd[-2:] == ["cat", "/etc/os-release"]:
            return _cp(0, os_release)
        if cmd[-3:] == ["bash", "-lc", expected_install]:
            install_seen["cmd"] = cmd[-1]
            return _cp(0)
        raise AssertionError(f"unexpected command: {cmd}")

    result = ensure_tmux("Any", auto_install=True, runner=runner)
    assert result.install_attempted is True
    assert install_seen["cmd"] == expected_install


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
