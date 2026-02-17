"""Git command and clone fallback utilities for runtime preflight."""

from __future__ import annotations

import logging as py_logging
import os
import subprocess
from collections.abc import Callable

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.runtime.wsl_discovery import build_wsl_command
from branchnexus.ui.runtime.constants import (
    WSL_GIT_CLONE_FULL_TIMEOUT_SECONDS,
    WSL_GIT_CLONE_PARTIAL_TIMEOUT_SECONDS,
    WSL_GIT_PROBE_TIMEOUT_SECONDS,
    WSL_GIT_TIMEOUT_SECONDS,
)
from branchnexus.ui.services.security import command_for_log, truncate_log
from branchnexus.ui.services.wsl_runner import (
    emit_terminal_progress,
    run_with_heartbeat,
    run_wsl_script,
)

logger = py_logging.getLogger(__name__)

_GIT_AUTH_FAILURE_MARKERS = (
    "authentication failed",
    "invalid credentials",
    "http basic: access denied",
    "could not read username",
    "fatal: could not read",
    "401",
    "403",
)

_TIMEOUT_FAILURE_MARKERS = (
    "zaman asimina ugradi",
    "timed out",
    "timeout",
)


def looks_like_git_auth_failure(value: str) -> bool:
    """Return True when git output suggests authentication failure."""
    text = value.lower()
    return any(marker in text for marker in _GIT_AUTH_FAILURE_MARKERS)


def looks_like_timeout_failure(value: str) -> bool:
    """Return True when error text indicates timeout semantics."""
    text = value.lower()
    return any(marker in text for marker in _TIMEOUT_FAILURE_MARKERS)


def is_legacy_worktree_path(path: str, *, workspace_root: str) -> bool:
    """Check if path belongs to the legacy runtime worktree location."""
    value = path.strip()
    if not value:
        return False
    legacy_root = f"{workspace_root.rstrip('/')}/.branchnexus-runtime/worktrees/"
    return value.startswith(legacy_root)


def normalize_branch_pair(branch: str) -> tuple[str, str]:
    """Return (local, remote) branch name pair for selected branch."""
    value = branch.strip()
    if not value:
        return "", ""
    if value.startswith("origin/"):
        local = value[7:].strip()
        if not local:
            return "", ""
        return local, value
    return value, f"origin/{value}"


def build_git_env(base_env: dict[str, str] | None, *, token: str) -> dict[str, str]:
    """Inject token-backed auth header into git environment."""
    env = dict(base_env or os.environ)
    token_value = token.strip()
    if not token_value:
        return env

    existing_count_raw = env.get("GIT_CONFIG_COUNT", "0")
    try:  # pragma: no cover
        existing_count = int(existing_count_raw)
    except ValueError:
        existing_count = 0

    slot = existing_count
    env["GIT_CONFIG_COUNT"] = str(existing_count + 1)
    env[f"GIT_CONFIG_KEY_{slot}"] = "http.extraheader"
    env[f"GIT_CONFIG_VALUE_{slot}"] = f"Authorization: Bearer {token_value}"
    return env


def run_wsl_git_argv(
    *,
    distribution: str,
    git_args: list[str],
    step: str,
    env: dict[str, str] | None = None,
    github_token: str = "",
    verbose_sink: Callable[[str], None] | None = None,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run a git command inside WSL with hardened environment defaults."""
    command = build_wsl_command(distribution, ["git", "-c", "credential.helper=", *git_args])
    run_env = build_git_env(env, token=github_token)
    run_env.setdefault("GIT_TERMINAL_PROMPT", "0")
    run_env.setdefault("GCM_INTERACTIVE", "never")
    run_env.setdefault("GIT_ASKPASS", "echo")
    run_env.setdefault("SSH_ASKPASS", "echo")
    logger.debug("runtime-open preflight-run step=%s command=%s", step, command_for_log(command))
    emit_terminal_progress(
        verbose_sink,
        level="RUN",
        step=step,
        message=f"command={command_for_log(command)}",
    )
    resolved_timeout = timeout_seconds or WSL_GIT_TIMEOUT_SECONDS
    try:
        result = run_with_heartbeat(
            command=command,
            env=run_env,
            timeout_seconds=resolved_timeout,
            step=step,
            verbose_sink=verbose_sink,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error("runtime-open preflight-timeout step=%s timeout=%ss", step, resolved_timeout)
        emit_terminal_progress(
            verbose_sink,
            level="TIMEOUT",
            step=step,
            message=f"timeout={resolved_timeout}s",
        )
        raise BranchNexusError(
            f"Runtime WSL hazirlik adimi zaman asimina ugradi: {step}",
            code=ExitCode.RUNTIME_ERROR,
            hint=(
                "Git komutu zaman asimina ugradi. "
                "Ag baglantisini ve depo erisim/kimlik ayarlarini kontrol edin."
            ),
        ) from exc
    if result.returncode == 0:
        logger.debug("runtime-open preflight-ok step=%s stdout=%s", step, truncate_log(result.stdout))
        emit_terminal_progress(verbose_sink, level="OK", step=step, message="git command completed")
        return result

    logger.error(
        "runtime-open preflight-fail step=%s code=%s stderr=%s",
        step,
        result.returncode,
        truncate_log(result.stderr),
    )
    emit_terminal_progress(
        verbose_sink,
        level="FAIL",
        step=step,
        message=f"code={result.returncode} stderr={truncate_log(result.stderr, limit=220)}",
    )
    raise BranchNexusError(
        f"Runtime WSL hazirlik adimi basarisiz: {step}",
        code=ExitCode.RUNTIME_ERROR,
        hint=result.stderr.strip() or "WSL git/tmux komutlarini kontrol edin.",
    )


def run_wsl_git_command(
    *,
    distribution: str,
    git_args: list[str],
    step: str,
    env: dict[str, str] | None = None,
    github_token: str = "",
    fallback_without_auth: bool = False,
    verbose_sink: Callable[[str], None] | None = None,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run WSL git command and optionally retry without auth header."""
    try:
        return run_wsl_git_argv(
            distribution=distribution,
            git_args=git_args,
            step=step,
            env=env,
            github_token=github_token,
            verbose_sink=verbose_sink,
            timeout_seconds=timeout_seconds,
        )
    except BranchNexusError as exc:
        if not (fallback_without_auth and github_token.strip()):
            raise
        details = f"{exc.message}\n{exc.hint}".strip()
        if not looks_like_git_auth_failure(details):
            raise

        logger.warning(
            "runtime-open git-auth-fallback step=%s reason=%s",
            step,
            truncate_log(details, limit=220),
        )
        emit_terminal_progress(
            verbose_sink,
            level="WARN",
            step=step,
            message=f"auth fallback: {truncate_log(details, limit=220)}",
        )
        return run_wsl_git_argv(
            distribution=distribution,
            git_args=git_args,
            step=f"{step}:no-auth",
            env=env,
            verbose_sink=verbose_sink,
            timeout_seconds=timeout_seconds,
        )


def clone_with_fallback(
    *,
    distribution: str,
    repo_url: str,
    anchor_path: str,
    repo_key: str,
    env: dict[str, str] | None,
    github_token: str,
    verbose_sink: Callable[[str], None] | None = None,
) -> None:
    """Clone repo in WSL using staged fallback paths."""
    from branchnexus.ui.services.github_service import clone_via_wsl_gh, parse_github_repo

    github_repo = parse_github_repo(repo_url)
    if github_repo:
        if clone_via_wsl_gh(
            distribution=distribution,
            repo_url=repo_url,
            anchor_path=anchor_path,
            repo_key=repo_key,
            env=env,
            github_token=github_token,
            verbose_sink=verbose_sink,
        ):
            return
        raise BranchNexusError(
            f"Runtime WSL hazirlik adimi basarisiz: repo-clone:{repo_key}:gh",
            code=ExitCode.RUNTIME_ERROR,
            hint=(
                "GitHub repo icin WSL gh clone tamamlanamadi. "
                "Uygulamadaki GitHub Anahtari alanina gecerli token girip tekrar deneyin."
            ),
        )

    probe_timed_out = False
    try:
        run_wsl_git_command(
            distribution=distribution,
            git_args=["ls-remote", "--heads", repo_url],
            step=f"repo-probe:{repo_key}",
            env=env,
            github_token=github_token,
            fallback_without_auth=True,
            verbose_sink=verbose_sink,
            timeout_seconds=WSL_GIT_PROBE_TIMEOUT_SECONDS,
        )
    except BranchNexusError as exc:
        details = f"{exc.message}\n{exc.hint}".strip()
        emit_terminal_progress(
            verbose_sink,
            level="WARN",
            step=f"repo-probe:{repo_key}",
            message=f"probe failed, continuing clone: {truncate_log(details, limit=220)}",
        )
        probe_timed_out = looks_like_timeout_failure(details)

    if probe_timed_out:
        emit_terminal_progress(
            verbose_sink,
            level="WARN",
            step=f"repo-clone:{repo_key}",
            message="probe timeout detected, continuing with WSL-only clone mode",
        )

    try:
        run_wsl_git_command(
            distribution=distribution,
            git_args=[
                "-c",
                "protocol.version=2",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                repo_url,
                anchor_path,
            ],
            step=f"repo-clone:{repo_key}:partial",
            env=env,
            github_token=github_token,
            fallback_without_auth=True,
            verbose_sink=verbose_sink,
            timeout_seconds=WSL_GIT_CLONE_PARTIAL_TIMEOUT_SECONDS,
        )
        return
    except BranchNexusError as exc:
        emit_terminal_progress(
            verbose_sink,
            level="WARN",
            step=f"repo-clone:{repo_key}",
            message=f"partial clone failed, retrying with full clone: {exc.message}",
        )
        run_wsl_script(
            distribution=distribution,
            script=f'rm -rf "{anchor_path}"',
            step=f"repo-clone-cleanup-partial:{repo_key}",
            env=env,
            verbose_sink=verbose_sink,
        )
        try:
            run_wsl_git_command(
                distribution=distribution,
                git_args=["clone", repo_url, anchor_path],
                step=f"repo-clone:{repo_key}:full",
                env=env,
                github_token=github_token,
                fallback_without_auth=True,
                verbose_sink=verbose_sink,
                timeout_seconds=WSL_GIT_CLONE_FULL_TIMEOUT_SECONDS,
            )
            return
        except BranchNexusError as full_exc:
            emit_terminal_progress(
                verbose_sink,
                level="WARN",
                step=f"repo-clone:{repo_key}",
                message=f"full clone failed in WSL-only mode: {full_exc.message}",
            )
            raise BranchNexusError(
                f"Runtime WSL hazirlik adimi basarisiz: repo-clone:{repo_key}:wsl-only",
                code=ExitCode.RUNTIME_ERROR,
                hint=(
                    full_exc.hint
                    or "WSL icinde `gh` kurulumunu/kimlik ayarini kontrol edip tekrar deneyin."
                ),
            ) from full_exc


def parse_worktree_map(payload: str) -> dict[str, str]:
    """Parse `git worktree list --porcelain` into branch->path map."""
    branch_to_path: dict[str, str] = {}
    current_path = ""
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if line.startswith("worktree "):
            current_path = line.split(" ", 1)[1].strip()
            continue
        if not current_path:
            continue
        if line.startswith("branch refs/heads/"):
            branch_name = line.removeprefix("branch refs/heads/").strip()
            if branch_name:
                branch_to_path[branch_name] = current_path
    return branch_to_path


def parse_worktree_paths(payload: str) -> set[str]:
    """Parse porcelain worktree list and return only path entries."""
    paths: set[str] = set()
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if line.startswith("worktree "):
            path = line.split(" ", 1)[1].strip()
            if path:
                paths.add(path)
    return paths


# Backward compatibility aliases during app.py extraction.
_is_legacy_runtime_worktree_path = is_legacy_worktree_path
_normalize_branch_pair = normalize_branch_pair
_git_env_with_auth = build_git_env
_run_wsl_git_argv = run_wsl_git_argv
_run_wsl_git_command = run_wsl_git_command
_clone_remote_repo_with_fallback = clone_with_fallback
_parse_worktree_branch_map = parse_worktree_map
_parse_worktree_paths = parse_worktree_paths
_looks_like_git_auth_failure = looks_like_git_auth_failure
_looks_like_timeout_failure = looks_like_timeout_failure
