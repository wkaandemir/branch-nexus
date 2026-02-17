from __future__ import annotations

import subprocess

import pytest

import branchnexus.ui.services.git_operations as git_ops
import branchnexus.ui.services.github_service as github_service


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_parse_github_repo_supports_https_and_ssh() -> None:
    assert (
        github_service.parse_github_repo("https://github.com/org/repo.git")
        == "org/repo"
    )
    assert github_service.parse_github_repo("git@github.com:org/repo.git") == "org/repo"
    assert github_service.parse_github_repo("https://gitlab.com/org/repo.git") == ""


def test_run_host_git_clone_requires_git_binary(monkeypatch) -> None:
    monkeypatch.setattr(github_service.shutil, "which", lambda _: None)
    with pytest.raises(github_service.BranchNexusError) as exc:
        github_service.run_host_git_clone(
            repo_url="https://github.com/org/repo.git",
            windows_target_path=r"C:\repo",
            github_token="ghp_secret",
            step="host-clone",
        )
    assert "Host git executable bulunamadi." in exc.value.message


def test_run_host_git_clone_falls_back_without_auth(monkeypatch) -> None:
    calls: list[list[str]] = []
    monkeypatch.setattr(github_service.shutil, "which", lambda _: "git")

    def fake_run_with_heartbeat(*, command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if len(calls) == 1:
            return _cp(1, stderr="fatal: Authentication failed")
        return _cp(0, stdout="ok")

    monkeypatch.setattr(github_service, "run_with_heartbeat", fake_run_with_heartbeat)
    github_service.run_host_git_clone(
        repo_url="https://github.com/org/repo.git",
        windows_target_path=r"C:\repo",
        github_token="ghp_secret",
        step="host-clone",
    )
    assert len(calls) == 2
    assert "http.extraheader=Authorization: Bearer ghp_secret" in " ".join(calls[0])
    assert "http.extraheader=Authorization: Bearer ghp_secret" not in " ".join(calls[1])


def test_ensure_wsl_gh_retries_install_as_root(monkeypatch) -> None:
    steps: list[tuple[str, str]] = []

    def fake_run_wsl_probe_script(*, step: str, script: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        steps.append((step, script))
        if step.startswith("gh-check:"):
            return _cp(1, stderr="missing")
        if step.startswith("gh-install:"):
            return _cp(1, stderr="sudo-password-required")
        if step.startswith("gh-install-root:"):
            return _cp(0, stdout="ok")
        raise AssertionError(f"unexpected step {step}")

    monkeypatch.setattr(github_service, "run_wsl_probe_script", fake_run_wsl_probe_script)
    ok = github_service.ensure_wsl_gh(distribution="Ubuntu", repo_key="repo")
    assert ok is True
    assert [name for name, _ in steps] == ["gh-check:repo", "gh-install:repo", "gh-install-root:repo"]


def test_clone_via_wsl_gh_returns_false_when_gh_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(github_service, "ensure_wsl_gh", lambda **kwargs: False)
    result = github_service.clone_via_wsl_gh(
        distribution="Ubuntu",
        repo_url="https://github.com/org/repo.git",
        anchor_path="/work/repo",
        repo_key="repo",
        env={},
        github_token="ghp_secret",
    )
    assert result is False


def test_clone_via_wsl_gh_requires_token(monkeypatch) -> None:
    monkeypatch.setattr(github_service, "ensure_wsl_gh", lambda **kwargs: True)
    with pytest.raises(github_service.BranchNexusError) as exc:
        github_service.clone_via_wsl_gh(
            distribution="Ubuntu",
            repo_url="https://github.com/org/repo.git",
            anchor_path="/work/repo",
            repo_key="repo",
            env={},
            github_token="",
        )
    assert "GitHub baglantisi icin GitHub Anahtari gerekli." in (exc.value.hint or "")


def test_clone_via_wsl_gh_uses_token_env(monkeypatch) -> None:
    seen_env: list[dict[str, str]] = []
    monkeypatch.setattr(github_service, "ensure_wsl_gh", lambda **kwargs: True)

    def fake_run_wsl_probe_script(
        *, step: str, env: dict[str, str] | None = None, input_text: str | None = None, **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if step.endswith(":gh"):
            assert input_text == "ghp_secret\n"
            seen_env.append(dict(env or {}))
        return _cp(0, stdout="ok")

    monkeypatch.setattr(github_service, "run_wsl_probe_script", fake_run_wsl_probe_script)
    result = github_service.clone_via_wsl_gh(
        distribution="Ubuntu",
        repo_url="https://github.com/org/repo.git",
        anchor_path="/work/repo",
        repo_key="repo",
        env={"PATH": "/usr/bin"},
        github_token="ghp_secret",
    )
    assert result is True
    assert seen_env[0]["BRANCHNEXUS_GH_TOKEN"] == "ghp_secret"
    assert seen_env[0]["GH_TOKEN"] == "ghp_secret"
    assert seen_env[0]["GITHUB_TOKEN"] == "ghp_secret"


def test_clone_via_wsl_gh_uses_git_fallback_after_gh_failure(monkeypatch) -> None:
    monkeypatch.setattr(github_service, "ensure_wsl_gh", lambda **kwargs: True)

    def fake_run_wsl_probe_script(*, step: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        if step.endswith(":gh"):
            return _cp(1, stderr="network failure")
        return _cp(0, stdout="ok")

    monkeypatch.setattr(github_service, "run_wsl_probe_script", fake_run_wsl_probe_script)
    called: list[str] = []

    def fake_run_wsl_git_command(*, step: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        called.append(step)
        return _cp(0, stdout="ok")

    monkeypatch.setattr(git_ops, "run_wsl_git_command", fake_run_wsl_git_command)
    result = github_service.clone_via_wsl_gh(
        distribution="Ubuntu",
        repo_url="https://github.com/org/repo.git",
        anchor_path="/work/repo",
        repo_key="repo",
        env={},
        github_token="ghp_secret",
    )
    assert result is True
    assert called == ["repo-clone:repo:git-fallback"]
