from __future__ import annotations

import subprocess

import pytest

import branchnexus.ui.services.git_operations as git_ops
import branchnexus.ui.services.github_service as github_service


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_wsl_git_command_uses_git_argv_and_env_auth(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["cmd"] = cmd
        seen["env"] = kwargs.get("env")
        return _cp(0, stdout="ok")

    monkeypatch.setattr(git_ops.subprocess, "run", fake_run)
    git_ops.run_wsl_git_command(
        distribution="Ubuntu",
        git_args=["fetch", "--prune"],
        step="repo-fetch",
        env={"PATH": "/usr/bin"},
        github_token="ghp_secret",
    )
    command = seen["cmd"]
    assert isinstance(command, list)
    assert command[:8] == [
        "wsl.exe",
        "-d",
        "Ubuntu",
        "--",
        "git",
        "-c",
        "credential.helper=",
        "fetch",
    ]
    env = seen["env"]
    assert isinstance(env, dict)
    assert env["GIT_CONFIG_VALUE_0"] == "Authorization: Bearer ghp_secret"
    assert env["GIT_TERMINAL_PROMPT"] == "0"


def test_run_wsl_git_command_falls_back_without_auth_on_auth_failure(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        env = dict(kwargs.get("env") or {})
        calls.append((cmd, env))
        if len(calls) == 1:
            return _cp(1, stderr="fatal: Authentication failed")
        return _cp(0, stdout="ok")

    monkeypatch.setattr(git_ops.subprocess, "run", fake_run)
    git_ops.run_wsl_git_command(
        distribution="Ubuntu",
        git_args=["clone", "https://github.com/org/repo.git", "/repo"],
        step="repo-clone",
        env={"PATH": "/usr/bin"},
        github_token="ghp_secret",
        fallback_without_auth=True,
    )
    assert len(calls) == 2
    _, first_env = calls[0]
    _, second_env = calls[1]
    assert "GIT_CONFIG_VALUE_0" in first_env
    assert "GIT_CONFIG_VALUE_0" not in second_env


def test_clone_with_fallback_uses_probe_and_full_retry(monkeypatch) -> None:
    git_steps: list[str] = []
    scripts: list[tuple[str, str]] = []

    def fake_run_wsl_git_command(*, step: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        git_steps.append(step)
        if step.endswith(":partial"):
            raise git_ops.BranchNexusError(
                "Runtime WSL hazirlik adimi basarisiz: repo-clone:create-post:partial",
                code=git_ops.ExitCode.RUNTIME_ERROR,
                hint="simulated failure",
            )
        return _cp(0, stdout="ok")

    def fake_run_wsl_script(
        *,
        distribution: str,
        script: str,
        step: str,
        env: dict[str, str] | None = None,
        verbose_sink: object | None = None,
    ) -> subprocess.CompletedProcess[str]:
        scripts.append((step, script))
        return _cp(0, stdout="ok")

    monkeypatch.setattr(git_ops, "run_wsl_git_command", fake_run_wsl_git_command)
    monkeypatch.setattr(git_ops, "run_wsl_script", fake_run_wsl_script)
    monkeypatch.setattr(github_service, "clone_via_wsl_gh", lambda **kwargs: False)
    git_ops.clone_with_fallback(
        distribution="Ubuntu",
        repo_url="https://gitlab.com/org/repo.git",
        anchor_path="/work/repo",
        repo_key="create-post",
        env={"PATH": "/usr/bin"},
        github_token="ghp_secret",
    )
    assert git_steps == ["repo-probe:create-post", "repo-clone:create-post:partial", "repo-clone:create-post:full"]
    assert scripts == [("repo-clone-cleanup-partial:create-post", 'rm -rf "/work/repo"')]


def test_clone_with_fallback_prefers_wsl_gh_for_github_urls(monkeypatch) -> None:
    monkeypatch.setattr(github_service, "clone_via_wsl_gh", lambda **kwargs: True)
    called = {"git": False}

    def fake_run_wsl_git_command(**kwargs: object) -> subprocess.CompletedProcess[str]:
        called["git"] = True
        return _cp(0)

    monkeypatch.setattr(git_ops, "run_wsl_git_command", fake_run_wsl_git_command)
    git_ops.clone_with_fallback(
        distribution="Ubuntu",
        repo_url="https://github.com/org/repo.git",
        anchor_path="/work/repo",
        repo_key="repo",
        env={"PATH": "/usr/bin"},
        github_token="ghp_secret",
    )
    assert called["git"] is False


def test_clone_with_fallback_requires_gh_for_github_urls(monkeypatch) -> None:
    monkeypatch.setattr(github_service, "clone_via_wsl_gh", lambda **kwargs: False)
    with pytest.raises(git_ops.BranchNexusError) as exc:
        git_ops.clone_with_fallback(
            distribution="Ubuntu",
            repo_url="https://github.com/org/repo.git",
            anchor_path="/work/repo",
            repo_key="repo",
            env={},
            github_token="ghp_secret",
        )
    assert ":gh" in exc.value.message


def test_parse_worktree_map_and_paths() -> None:
    payload = "\n".join(
        [
            "worktree /repos/a",
            "branch refs/heads/main",
            "worktree /repos/b",
            "branch refs/heads/feature-x",
        ]
    )
    mapping = git_ops.parse_worktree_map(payload)
    paths = git_ops.parse_worktree_paths(payload)
    assert mapping == {"main": "/repos/a", "feature-x": "/repos/b"}
    assert paths == {"/repos/a", "/repos/b"}


def test_normalize_branch_pair_handles_origin_plain_and_empty() -> None:
    assert git_ops.normalize_branch_pair("origin/main") == ("main", "origin/main")
    assert git_ops.normalize_branch_pair("feature-x") == ("feature-x", "origin/feature-x")
    assert git_ops.normalize_branch_pair("") == ("", "")


def test_is_legacy_worktree_path_detects_prefix() -> None:
    workspace = "/home/demo/branchnexus-workspace"
    legacy = "/home/demo/branchnexus-workspace/.branchnexus-runtime/worktrees/repo/pane-1"
    modern = "/home/demo/branchnexus-workspace/.bnx/w/repo/p1"
    assert git_ops.is_legacy_worktree_path(legacy, workspace_root=workspace) is True
    assert git_ops.is_legacy_worktree_path(modern, workspace_root=workspace) is False


def test_failure_marker_helpers_detect_expected_markers() -> None:
    assert git_ops.looks_like_git_auth_failure("fatal: Authentication failed")
    assert git_ops.looks_like_timeout_failure("operation timed out")
