from __future__ import annotations

import subprocess

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.git.materialize import materialize_remote_branch


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_materialize_creates_local_branch_when_missing() -> None:
    calls: list[str] = []

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        key = " ".join(cmd[3:])
        calls.append(key)
        if key == "branch --list feature":
            return _cp(0, "")
        if key == "branch --track feature origin/feature":
            return _cp(0)
        raise AssertionError(key)

    branch = materialize_remote_branch("/repo", "origin/feature", runner=runner)
    assert branch == "feature"
    assert "branch --track feature origin/feature" in calls


def test_materialize_is_idempotent_when_local_exists() -> None:
    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        key = " ".join(cmd[3:])
        if key == "branch --list main":
            return _cp(0, "main\n")
        raise AssertionError(key)

    assert materialize_remote_branch("/repo", "origin/main", runner=runner) == "main"


def test_materialize_does_not_delete_branch_on_create_failure() -> None:
    calls: list[str] = []

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        key = " ".join(cmd[3:])
        calls.append(key)
        if key == "branch --list feature":
            return _cp(0, "")
        if key == "branch --track feature origin/feature":
            return _cp(1, stderr="failed")
        raise AssertionError(key)

    with pytest.raises(BranchNexusError):
        materialize_remote_branch("/repo", "origin/feature", runner=runner)
    assert "branch -D feature" not in calls


def test_materialize_normalizes_wsl_repo_path_argument() -> None:
    seen_repo = {"value": ""}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        seen_repo["value"] = cmd[2]
        key = " ".join(cmd[3:])
        if key == "branch --list main":
            return _cp(0, "main\n")
        raise AssertionError(key)

    assert materialize_remote_branch(r"\mnt\c\Users\demo\repo", "origin/main", runner=runner) == "main"
    assert seen_repo["value"] == "/mnt/c/Users/demo/repo"
