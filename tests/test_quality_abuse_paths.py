from __future__ import annotations

import subprocess

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.git.github_repositories import list_github_repository_branches
from branchnexus.git.remote_workspace import list_remote_branches_in_repo, repo_name_from_url
from branchnexus.runtime.wsl_discovery import build_wsl_command
from branchnexus.runtime.wsl_runtime import WslRuntime


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_repo_name_from_url_rejects_invalid_values() -> None:
    with pytest.raises(BranchNexusError):
        repo_name_from_url("   ")


@pytest.mark.security
def test_remote_branch_listing_shell_quotes_repo_path() -> None:
    captured: dict[str, list[str]] = {}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        captured["cmd"] = cmd
        return _cp(0, "origin/main\n")

    list_remote_branches_in_repo(
        distribution="Ubuntu",
        repo_path_wsl="/work/repo; echo exploited",
        runner=runner,
    )

    # Command payload must be shell-quoted, so separator chars stay inside a literal path.
    assert captured["cmd"][-1].startswith("git -C '/work/repo; echo exploited'")


@pytest.mark.security
def test_build_wsl_command_rejects_empty_distribution() -> None:
    with pytest.raises(BranchNexusError):
        build_wsl_command("", ["git", "status"])


@pytest.mark.security
def test_build_wsl_command_rejects_empty_command() -> None:
    with pytest.raises(BranchNexusError):
        build_wsl_command("Ubuntu", [])


@pytest.mark.security
def test_github_branches_handles_rate_limit_error() -> None:
    def requester(_: str, __: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        return 429, '{"message":"API rate limit exceeded"}', {}

    with pytest.raises(BranchNexusError) as exc:
        list_github_repository_branches("token", "org/repo", requester=requester)

    assert "429" in str(exc.value)


@pytest.mark.security
def test_github_branches_handles_server_error() -> None:
    def requester(_: str, __: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        return 500, '{"message":"Internal Server Error"}', {}

    with pytest.raises(BranchNexusError) as exc:
        list_github_repository_branches("token", "org/repo", requester=requester)

    assert "500" in str(exc.value)


def test_wsl_runtime_non_transient_failure_does_not_retry() -> None:
    attempts = {"count": 0}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        attempts["count"] += 1
        return _cp(1, stderr="fatal: repository not found")

    runtime = WslRuntime("Ubuntu", runner=runner, max_retries=3)
    with pytest.raises(BranchNexusError):
        runtime.run(["git", "status"])

    assert attempts["count"] == 1
