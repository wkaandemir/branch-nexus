from __future__ import annotations

import subprocess
from pathlib import PurePosixPath

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.git.remote_workspace import (
    ensure_remote_repo_synced,
    list_remote_branches_in_repo,
    list_workspace_repositories,
    repo_name_from_url,
    resolve_wsl_home_directory,
)

pytestmark = pytest.mark.critical_regression


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_repo_name_from_url() -> None:
    assert repo_name_from_url("https://github.com/org/repo.git") == "repo"
    assert repo_name_from_url("git@github.com:org/repo") == "repo"


def test_resolve_wsl_home_directory() -> None:
    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        inner = cmd[4:]
        if inner[:2] == ["bash", "-lc"]:
            return _cp(0, stdout="/home/demo")
        raise AssertionError(inner)

    assert resolve_wsl_home_directory(distribution="Ubuntu", runner=runner) == PurePosixPath("/home/demo")


def test_resolve_wsl_home_directory_raises_on_failure() -> None:
    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        inner = cmd[4:]
        if inner[:2] == ["bash", "-lc"]:
            return _cp(1, stderr="bash failed")
        raise AssertionError(inner)

    with pytest.raises(BranchNexusError):
        resolve_wsl_home_directory(distribution="Ubuntu", runner=runner)


def test_clone_when_repo_missing() -> None:
    commands: list[list[str]] = []

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        commands.append(cmd)
        inner = cmd[4:]
        if inner[:2] == ["bash", "-lc"]:
            return _cp(1)
        if inner[:2] == ["mkdir", "-p"]:
            return _cp(0)
        if inner[:2] == ["git", "clone"]:
            return _cp(0)
        if inner[:5] == ["git", "-C", "/work/repo", "checkout", "--detach"]:
            return _cp(0)
        raise AssertionError(inner)

    path = ensure_remote_repo_synced(
        distribution="Ubuntu",
        repo_url="https://github.com/org/repo.git",
        workspace_root_wsl="/work",
        runner=runner,
    )
    assert path == PurePosixPath("/work/repo")
    assert any(cmd[4:6] == ["git", "clone"] for cmd in commands)
    assert any(cmd[4:9] == ["git", "-C", "/work/repo", "checkout", "--detach"] for cmd in commands)


def test_fetch_when_repo_exists() -> None:
    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        inner = cmd[4:]
        if inner[:2] == ["bash", "-lc"]:
            return _cp(0)
        if inner[:4] == ["git", "-C", "/work/repo", "fetch"]:
            return _cp(0)
        if inner[:5] == ["git", "-C", "/work/repo", "checkout", "--detach"]:
            return _cp(0)
        raise AssertionError(inner)

    path = ensure_remote_repo_synced(
        distribution="Ubuntu",
        repo_url="https://github.com/org/repo.git",
        workspace_root_wsl="/work",
        runner=runner,
    )
    assert path == PurePosixPath("/work/repo")


def test_sync_raises_if_detach_fails() -> None:
    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        inner = cmd[4:]
        if inner[:2] == ["bash", "-lc"]:
            return _cp(0)
        if inner[:4] == ["git", "-C", "/work/repo", "fetch"]:
            return _cp(0)
        if inner[:5] == ["git", "-C", "/work/repo", "checkout", "--detach"]:
            return _cp(1, stderr="detach failed")
        raise AssertionError(inner)

    with pytest.raises(BranchNexusError):
        ensure_remote_repo_synced(
            distribution="Ubuntu",
            repo_url="https://github.com/org/repo.git",
            workspace_root_wsl="/work",
            runner=runner,
        )


def test_list_remote_branches() -> None:
    runner = lambda *args, **kwargs: _cp(0, "origin/main\norigin/feature\norigin/HEAD -> origin/main\n")
    branches = list_remote_branches_in_repo(
        distribution="Ubuntu",
        repo_path_wsl="/work/repo",
        runner=runner,
    )
    assert branches == ["origin/feature", "origin/main"]


def test_list_remote_branches_raises_when_empty() -> None:
    runner = lambda *args, **kwargs: _cp(0, "")
    with pytest.raises(BranchNexusError):
        list_remote_branches_in_repo(distribution="Ubuntu", repo_path_wsl="/work/repo", runner=runner)


def test_list_workspace_repositories_discovers_git_dirs() -> None:
    runner = lambda *args, **kwargs: _cp(0, "/work/a/.git\n/work/b/.git\n/work/a/.git\n")
    repositories = list_workspace_repositories(
        distribution="Ubuntu",
        workspace_root_wsl="/work",
        runner=runner,
    )
    assert repositories == [PurePosixPath("/work/a"), PurePosixPath("/work/b")]


def test_list_workspace_repositories_raises_on_failure() -> None:
    runner = lambda *args, **kwargs: _cp(1, stderr="find failed")
    with pytest.raises(BranchNexusError):
        list_workspace_repositories(
            distribution="Ubuntu",
            workspace_root_wsl="/work",
            runner=runner,
        )
