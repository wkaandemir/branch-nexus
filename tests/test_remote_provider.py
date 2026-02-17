from __future__ import annotations

import subprocess

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.git.remote_provider import fetch_and_list


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_remote_provider_returns_local_and_remote_sets() -> None:
    responses = {
        "rev-parse --is-inside-work-tree": _cp(0, "true\n"),
        "symbolic-ref --short -q HEAD": _cp(0, "main\n"),
        "branch --format=%(refname:short)": _cp(0, "main\nfeature\n"),
        "fetch --prune": _cp(0),
        "branch -r --format=%(refname:short)": _cp(0, "origin/main\norigin/feature\norigin/HEAD -> origin/main\n"),
    }

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        return responses[" ".join(cmd[3:])]

    result = fetch_and_list("/repo", runner=runner)
    assert result.local == ["feature", "main"]
    assert result.remote == ["origin/feature", "origin/main"]
    assert result.warning == ""


def test_remote_provider_degrades_when_fetch_fails() -> None:
    responses = {
        "rev-parse --is-inside-work-tree": _cp(0, "true\n"),
        "symbolic-ref --short -q HEAD": _cp(0, "main\n"),
        "branch --format=%(refname:short)": _cp(0, "main\n"),
        "fetch --prune": _cp(1, stderr="network"),
    }

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        return responses[" ".join(cmd[3:])]

    result = fetch_and_list("/repo", runner=runner)
    assert result.local == ["main"]
    assert result.remote == []
    assert "Remote fetch failed" in result.warning


def test_remote_provider_raises_when_remote_listing_fails() -> None:
    responses = {
        "rev-parse --is-inside-work-tree": _cp(0, "true\n"),
        "symbolic-ref --short -q HEAD": _cp(0, "main\n"),
        "branch --format=%(refname:short)": _cp(0, "main\n"),
        "fetch --prune": _cp(0),
        "branch -r --format=%(refname:short)": _cp(1, stderr="permission denied"),
    }

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        return responses[" ".join(cmd[3:])]

    with pytest.raises(BranchNexusError) as exc:
        fetch_and_list("/repo", runner=runner)

    assert "Failed to list remote branches" in exc.value.message
