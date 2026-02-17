from __future__ import annotations

import subprocess

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.runtime.wsl_discovery import (
    _decode_process_output,
    build_wsl_command,
    distribution_unreachable_message,
    list_distributions,
    to_wsl_path,
    validate_distribution,
)


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_list_distributions_returns_sorted_values() -> None:
    runner = lambda *args, **kwargs: _cp(0, "Ubuntu\nDebian\n")
    assert list_distributions(runner=runner) == ["Debian", "Ubuntu"]


def test_list_distributions_raises_on_command_failure() -> None:
    runner = lambda *args, **kwargs: _cp(1, stderr="failed")
    with pytest.raises(BranchNexusError):
        list_distributions(runner=runner)


def test_list_distributions_raises_on_empty_output() -> None:
    runner = lambda *args, **kwargs: _cp(0, "\n")
    with pytest.raises(BranchNexusError):
        list_distributions(runner=runner)


def test_build_wsl_command() -> None:
    cmd = build_wsl_command("Ubuntu", ["git", "status"])
    assert cmd == ["wsl.exe", "-d", "Ubuntu", "--", "git", "status"]


def test_validate_distribution_and_unreachable_message() -> None:
    assert validate_distribution("Ubuntu", ["Ubuntu", "Debian"])
    assert "Ubuntu" in distribution_unreachable_message("Ubuntu")


def test_decode_handles_utf16le_output() -> None:
    raw = "Ubuntu\nDebian\n".encode("utf-16le")
    assert _decode_process_output(raw) == "Ubuntu\nDebian\n"


def test_to_wsl_path_converts_windows_paths() -> None:
    seen: dict[str, list[str]] = {}

    def runner(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess:
        seen["cmd"] = cmd
        return _cp(0, b"/mnt/c/Users/test/repo\n")

    assert to_wsl_path("Ubuntu", r"C:\Users\test\repo", runner=runner) == "/mnt/c/Users/test/repo"
    assert seen["cmd"][-1] == "C:/Users/test/repo"


def test_to_wsl_path_uses_fallback_on_wslpath_failure() -> None:
    runner = lambda *args, **kwargs: _cp(1, b"", b"wslpath failed")
    assert to_wsl_path("Ubuntu", r"C:\Users\test\repo", runner=runner) == "/mnt/c/Users/test/repo"


def test_to_wsl_path_passthrough_when_already_wsl_path() -> None:
    assert to_wsl_path("Ubuntu", "/home/test/repo", runner=lambda *args, **kwargs: _cp(1)) == "/home/test/repo"


def test_to_wsl_path_raises_for_unconvertible_path() -> None:
    runner = lambda *args, **kwargs: _cp(1, b"", b"wslpath failed")
    with pytest.raises(BranchNexusError):
        to_wsl_path("Ubuntu", r"\\network\share\repo", runner=runner)
