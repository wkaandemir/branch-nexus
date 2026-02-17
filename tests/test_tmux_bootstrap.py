from __future__ import annotations

import subprocess

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.tmux.bootstrap import ensure_tmux


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_tmux_existing_skips_install() -> None:
    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(0, "/usr/bin/tmux\n")
        raise AssertionError("unexpected command")

    result = ensure_tmux("Ubuntu", auto_install=True, runner=runner)
    assert result.tmux_available is True
    assert result.install_attempted is False


def test_tmux_missing_attempts_noninteractive_install() -> None:
    seen_install = {"called": False}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(1)
        if cmd[-2:] == ["cat", "/etc/os-release"]:
            return _cp(0, "ID=ubuntu\n")
        # _try_noninteractive_install adds -n to the plain sudo command
        if cmd[-3:] == ["bash", "-lc", "sudo -n apt-get update && sudo -n apt-get install -y tmux"]:
            seen_install["called"] = True
            return _cp(0)
        raise AssertionError(f"unexpected command: {cmd}")

    result = ensure_tmux("Ubuntu", auto_install=True, runner=runner)
    assert result.install_attempted is True
    assert seen_install["called"]


def test_tmux_missing_and_install_fails_raises_manual_guidance() -> None:
    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        if cmd[-3:] == ["command", "-v", "tmux"]:
            return _cp(1)
        if cmd[-2:] == ["cat", "/etc/os-release"]:
            return _cp(0, "ID=ubuntu\n")
        # Non-interactive install fails (triggers interactive path)
        if cmd[-3:] == ["bash", "-lc", "sudo -n apt-get update && sudo -n apt-get install -y tmux"]:
            return _cp(1, stderr="password required")
        raise AssertionError(f"unexpected command: {cmd}")

    with pytest.raises(BranchNexusError) as exc:
        ensure_tmux("Ubuntu", auto_install=True, runner=runner)
    assert "Run this inside WSL" in str(exc.value)
