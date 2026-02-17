from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.git.branch_provider import list_local_branches


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_local_branches_are_sorted_and_stable() -> None:
    responses = {
        "rev-parse --is-inside-work-tree": _cp(0, "true\n"),
        "symbolic-ref --short -q HEAD": _cp(0, "main\n"),
        "branch --format=%(refname:short)": _cp(0, "feature/z\nmain\nfeature/a\n"),
    }

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        key = " ".join(cmd[3:])
        return responses[key]

    result = list_local_branches(Path("/tmp/repo"), runner=runner)
    assert result.branches == ["feature/a", "feature/z", "main"]
    assert result.warning == ""


def test_detached_head_returns_warning() -> None:
    responses = {
        "rev-parse --is-inside-work-tree": _cp(0, "true\n"),
        "symbolic-ref --short -q HEAD": _cp(1),
        "branch --format=%(refname:short)": _cp(0, "main\n"),
    }

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        return responses[" ".join(cmd[3:])]

    result = list_local_branches("/tmp/repo", runner=runner)
    assert "Detached HEAD" in result.warning


def test_empty_repo_raises_actionable_error() -> None:
    responses = {
        "rev-parse --is-inside-work-tree": _cp(0, "true\n"),
        "symbolic-ref --short -q HEAD": _cp(1),
        "branch --format=%(refname:short)": _cp(0, ""),
    }

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        return responses[" ".join(cmd[3:])]

    with pytest.raises(BranchNexusError) as exc:
        list_local_branches("/tmp/repo", runner=runner)
    assert "No local branches" in str(exc.value)
