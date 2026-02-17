"""GitHub/host-clone helpers for WSL runtime preflight."""

from __future__ import annotations

import logging as py_logging
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from contextlib import suppress

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.runtime.wsl_discovery import build_wsl_command
from branchnexus.ui.runtime.constants import (
    GITHUB_HTTPS_REPO_PATTERN,
    GITHUB_SSH_REPO_PATTERN,
    HOST_GIT_CLONE_TIMEOUT_SECONDS,
    WSL_GH_CLONE_TIMEOUT_SECONDS,
)
from branchnexus.ui.services.security import command_for_log, truncate_log
from branchnexus.ui.services.wsl_runner import (
    emit_terminal_progress,
    run_with_heartbeat,
    run_wsl_probe_script,
)

logger = py_logging.getLogger(__name__)

_GH_AUTH_FAILURE_MARKERS = (
    "authentication required",
    "requires authentication",
    "not logged in",
    "gh auth login",
    "gh_token environment variable",
    "to get started with github cli",
    "http 401",
    "http 403",
    "forbidden",
)


def parse_github_repo(repo_url: str) -> str:
    """Extract owner/repo from GitHub HTTPS or SSH URL."""
    value = repo_url.strip()
    if not value:
        return ""
    https_match = GITHUB_HTTPS_REPO_PATTERN.match(value)
    if https_match:
        owner, name = https_match.groups()
        return f"{owner}/{name}"
    ssh_match = GITHUB_SSH_REPO_PATTERN.match(value)
    if ssh_match:
        owner, name = ssh_match.groups()
        return f"{owner}/{name}"
    return ""


def _is_wsl_windows_mount_path(path: str) -> bool:
    value = path.strip()
    return bool(re.match(r"^/mnt/[a-zA-Z]/", value))


def _is_wsl_home_path(path: str) -> bool:
    value = path.strip()
    return value.startswith("/home/") or value.startswith("/root/")


def _should_try_host_bridge_for_wsl_path(path: str) -> bool:
    return _is_wsl_windows_mount_path(path) or _is_wsl_home_path(path)


def looks_like_gh_auth_failure(value: str) -> bool:
    """Return True when gh output indicates authentication failure."""
    from branchnexus.ui.services.git_operations import looks_like_git_auth_failure

    text = value.lower()
    if any(marker in text for marker in _GH_AUTH_FAILURE_MARKERS):
        return True
    return looks_like_git_auth_failure(value)


def ensure_wsl_gh(
    *,
    distribution: str,
    repo_key: str,
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> bool:
    """Ensure GitHub CLI is available inside WSL distro."""
    check_step = f"gh-check:{repo_key}"
    check = run_wsl_probe_script(
        distribution=distribution,
        script="command -v gh >/dev/null 2>&1",
        step=check_step,
        env=env,
        verbose_sink=verbose_sink,
    )
    if check.returncode == 0:
        emit_terminal_progress(
            verbose_sink,
            level="INFO",
            step=check_step,
            message="gh already available in WSL",
        )
        return True

    install_script = (
        "if command -v gh >/dev/null 2>&1; then exit 0; fi; "
        'if ! command -v apt-get >/dev/null 2>&1; then echo "apt-get-not-found" >&2; exit 43; fi; '
        'if command -v sudo >/dev/null 2>&1; then '
        'install_cmd="sudo -n apt-get update && sudo -n apt-get install -y gh"; '
        'elif [ "$(id -u)" = "0" ]; then install_cmd="apt-get update && apt-get install -y gh"; '
        'else echo "sudo-password-required" >&2; exit 42; fi; '
        'if command -v timeout >/dev/null 2>&1; then timeout 120s bash -lc "$install_cmd"; '
        'else bash -lc "$install_cmd"; fi; '
        "command -v gh >/dev/null 2>&1"
    )
    install_step = f"gh-install:{repo_key}"
    install = run_wsl_probe_script(
        distribution=distribution,
        script=install_script,
        step=install_step,
        env=env,
        verbose_sink=verbose_sink,
    )
    if install.returncode == 0:
        emit_terminal_progress(
            verbose_sink,
            level="INFO",
            step=install_step,
            message="gh installed in WSL",
        )
        return True

    details = (install.stderr or install.stdout or "").strip()
    emit_terminal_progress(
        verbose_sink,
        level="WARN",
        step=install_step,
        message=(
            "gh install failed for current user, retrying as root in WSL "
            f"details={truncate_log(details, limit=180)}"
        ),
    )
    install_root_script = (
        "if command -v gh >/dev/null 2>&1; then exit 0; fi; "
        "if ! command -v apt-get >/dev/null 2>&1; then exit 43; fi; "
        "export DEBIAN_FRONTEND=noninteractive; "
        "apt-get update; "
        "apt-get install -y curl ca-certificates gnupg >/dev/null 2>&1 || true; "
        "install -d -m 0755 /etc/apt/keyrings; "
        "if [ ! -f /etc/apt/keyrings/githubcli-archive-keyring.gpg ]; then "
        "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg "
        "-o /etc/apt/keyrings/githubcli-archive-keyring.gpg; "
        "chmod a+r /etc/apt/keyrings/githubcli-archive-keyring.gpg; "
        "fi; "
        'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] '
        'https://cli.github.com/packages stable main" '
        "> /etc/apt/sources.list.d/github-cli.list; "
        "apt-get update && apt-get install -y gh && command -v gh >/dev/null 2>&1"
    )
    install_root_step = f"gh-install-root:{repo_key}"
    install_root = run_wsl_probe_script(
        distribution=distribution,
        script=install_root_script,
        step=install_root_step,
        user="root",
        env=env,
        verbose_sink=verbose_sink,
    )
    if install_root.returncode == 0:
        emit_terminal_progress(
            verbose_sink,
            level="INFO",
            step=install_root_step,
            message="gh installed in WSL via root",
        )
        return True

    root_details = (install_root.stderr or install_root.stdout or "").strip()
    emit_terminal_progress(
        verbose_sink,
        level="WARN",
        step=install_root_step,
        message=(
            "gh install skipped/failed: "
            f"user={truncate_log(details, limit=140)} "
            f"root={truncate_log(root_details, limit=140)}"
        ),
    )
    return False


def clone_via_wsl_gh(
    *,
    distribution: str,
    repo_url: str,
    anchor_path: str,
    repo_key: str,
    env: dict[str, str] | None,
    github_token: str,
    verbose_sink: Callable[[str], None] | None = None,
) -> bool:
    """Try gh clone in WSL, then fallback to git clone variants."""
    from branchnexus.ui.services.git_operations import run_wsl_git_command

    token = github_token.strip()
    repo_full_name = parse_github_repo(repo_url)
    if not repo_full_name:
        return False
    if not token:
        raise BranchNexusError(
            f"Runtime WSL hazirlik adimi basarisiz: repo-clone:{repo_key}:gh-auth",
            code=ExitCode.RUNTIME_ERROR,
            hint=(
                "GitHub baglantisi icin GitHub Anahtari gerekli. "
                "Uygulamadaki GitHub Anahtari alanina gecerli token girin."
            ),
        )
    if not ensure_wsl_gh(
        distribution=distribution,
        repo_key=repo_key,
        env=env,
        verbose_sink=verbose_sink,
    ):
        return False

    emit_terminal_progress(
        verbose_sink,
        level="INFO",
        step=f"repo-auth:{repo_key}",
        message=f"token_present={'yes' if bool(token) else 'no'} token_len={len(token)}",
    )
    clone_env = dict(env or {})
    clone_env["BRANCHNEXUS_GH_TOKEN"] = token
    clone_env["GH_TOKEN"] = token
    clone_env["GITHUB_TOKEN"] = token
    clone_step = f"repo-clone:{repo_key}:gh"
    quoted_repo = shlex.quote(repo_full_name)
    quoted_anchor = shlex.quote(anchor_path)
    quoted_token = shlex.quote(token)
    clone_script = (
        f"token={quoted_token}; "
        'if [ -z "$token" ]; then token="${BRANCHNEXUS_GH_TOKEN:-${GH_TOKEN:-${GITHUB_TOKEN:-}}}"; fi; '
        'if [ -z "$token" ]; then token="$(cat)"; fi; '
        'if [ -z "$token" ]; then exit 21; fi; '
        'export GH_TOKEN="$token"; '
        'export GITHUB_TOKEN="$token"; '
        'export GIT_HTTP_VERSION="HTTP/1.1"; '
        'export GIT_PROTOCOL="version=2"; '
        "if command -v timeout >/dev/null 2>&1; then "
        + f"timeout {WSL_GH_CLONE_TIMEOUT_SECONDS}s gh repo clone {quoted_repo} {quoted_anchor} "
        + "-- --filter=blob:none --no-checkout; "
        + "else "
        + f"gh repo clone {quoted_repo} {quoted_anchor} -- --filter=blob:none --no-checkout; "
        + "fi"
    )
    try:
        clone = run_wsl_probe_script(
            distribution=distribution,
            script=clone_script,
            step=clone_step,
            input_text=f"{token}\n",
            env=clone_env,
            verbose_sink=verbose_sink,
        )
    except BranchNexusError as exc:
        emit_terminal_progress(
            verbose_sink,
            level="WARN",
            step=clone_step,
            message=f"gh clone failed: {exc.message}",
        )
        with suppress(BranchNexusError):
            run_wsl_probe_script(
                distribution=distribution,
                script=f"rm -rf {quoted_anchor}",
                step=f"repo-clone-cleanup-gh:{repo_key}",
                env=clone_env,
                verbose_sink=verbose_sink,
            )
        return False

    if clone.returncode == 0:
        emit_terminal_progress(
            verbose_sink,
            level="OK",
            step=clone_step,
            message=f"gh repo clone completed repo={repo_full_name}",
        )
        return True

    details = (clone.stderr or clone.stdout or "").strip()
    auth_failure = looks_like_gh_auth_failure(details)
    host_bridge_hint = ""
    emit_terminal_progress(
        verbose_sink,
        level="WARN",
        step=clone_step,
        message=(
            "gh clone auth failure, retrying token-authenticated git clone in WSL"
            if auth_failure
            else "gh clone failed, retrying token-authenticated git clone in WSL"
        ),
    )
    if _should_try_host_bridge_for_wsl_path(anchor_path):
        host_step = f"repo-clone:{repo_key}:host-bridge"
        emit_terminal_progress(
            verbose_sink,
            level="WARN",
            step=host_step,
            message="WSL hedefi icin host git bridge ile clone deneniyor",
        )
        with suppress(BranchNexusError):
            run_wsl_probe_script(
                distribution=distribution,
                script=f"rm -rf {quoted_anchor}",
                step=f"repo-clone-cleanup-host:{repo_key}",
                env=clone_env,
                verbose_sink=verbose_sink,
            )
        try:
            clone_via_host_git(
                distribution=distribution,
                repo_url=repo_url,
                anchor_path=anchor_path,
                repo_key=repo_key,
                github_token=token,
                verbose_sink=verbose_sink,
            )
            return True
        except BranchNexusError as host_exc:
            host_bridge_hint = (host_exc.hint or host_exc.message).strip()
            emit_terminal_progress(
                verbose_sink,
                level="WARN",
                step=host_step,
                message=(
                    "host bridge clone basarisiz, WSL fallback devam ediyor: "
                    f"{truncate_log(host_bridge_hint, limit=220)}"
                ),
            )

    fallback_step = f"repo-clone:{repo_key}:git-fallback"
    with suppress(BranchNexusError):
        run_wsl_probe_script(
            distribution=distribution,
            script=f"rm -rf {quoted_anchor}",
            step=f"repo-clone-cleanup-gh:{repo_key}",
            env=clone_env,
            verbose_sink=verbose_sink,
        )
    try:
        run_wsl_git_command(
            distribution=distribution,
            git_args=[
                "-c",
                "protocol.version=2",
                "-c",
                "http.version=HTTP/1.1",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                repo_url,
                anchor_path,
            ],
            step=fallback_step,
            env=clone_env,
            github_token=token,
            fallback_without_auth=False,
            verbose_sink=verbose_sink,
            timeout_seconds=WSL_GH_CLONE_TIMEOUT_SECONDS,
        )
        emit_terminal_progress(
            verbose_sink,
            level="OK",
            step=fallback_step,
            message="git clone fallback completed",
        )
        return True
    except BranchNexusError as fallback_exc:
        fallback_details = (fallback_exc.hint or fallback_exc.message).strip()

    public_try_step = f"repo-clone:{repo_key}:public-no-auth"
    should_try_public_no_auth = not auth_failure
    no_auth_error_hint = ""
    if should_try_public_no_auth:
        emit_terminal_progress(
            verbose_sink,
            level="WARN",
            step=public_try_step,
            message="token-auth clone failed, retrying public clone without auth",
        )
        with suppress(BranchNexusError):
            run_wsl_probe_script(
                distribution=distribution,
                script=f"rm -rf {quoted_anchor}",
                step=f"repo-clone-cleanup-public:{repo_key}",
                env=clone_env,
                verbose_sink=verbose_sink,
            )
        no_auth_env = dict(clone_env)
        no_auth_env.pop("BRANCHNEXUS_GH_TOKEN", None)
        no_auth_env.pop("GH_TOKEN", None)
        no_auth_env.pop("GITHUB_TOKEN", None)
        try:
            run_wsl_git_command(
                distribution=distribution,
                git_args=[
                    "-c",
                    "protocol.version=2",
                    "-c",
                    "http.version=HTTP/1.1",
                    "clone",
                    "--filter=blob:none",
                    "--no-checkout",
                    repo_url,
                    anchor_path,
                ],
                step=public_try_step,
                env=no_auth_env,
                github_token="",
                fallback_without_auth=False,
                verbose_sink=verbose_sink,
                timeout_seconds=WSL_GH_CLONE_TIMEOUT_SECONDS,
            )
            emit_terminal_progress(
                verbose_sink,
                level="OK",
                step=public_try_step,
                message="public clone completed",
            )
            return True
        except BranchNexusError as no_auth_exc:
            no_auth_error_hint = no_auth_exc.hint or no_auth_exc.message

    detail_hint = (
        no_auth_error_hint
        or fallback_details
        or host_bridge_hint
        or details
        or "WSL gh/git clone loglarini kontrol edin."
    )
    if auth_failure and looks_like_gh_auth_failure(detail_hint):
        detail_hint = (
            "GitHub Anahtari gecersiz veya yetkisiz. "
            "Uygulamadaki GitHub Anahtari alanina gecerli token girin."
        )
    raise BranchNexusError(
        f"Runtime WSL hazirlik adimi basarisiz: "
        f"{public_try_step if should_try_public_no_auth else fallback_step}",
        code=ExitCode.RUNTIME_ERROR,
        hint=truncate_log(detail_hint, limit=320),
    )


def windows_to_wsl_path(
    *,
    distribution: str,
    wsl_path: str,
    env: dict[str, str] | None = None,
) -> str:
    """Convert a WSL path into host Windows path using wslpath."""
    command = build_wsl_command(distribution, ["wslpath", "-w", wsl_path])
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
        timeout=30,
    )
    path = (result.stdout or "").strip()
    if result.returncode == 0 and path:
        return path
    raise BranchNexusError(
        f"WSL path Windows yoluna cevrilemedi: {wsl_path}",
        code=ExitCode.RUNTIME_ERROR,
        hint=result.stderr.strip() or "wslpath -w komutunu kontrol edin.",
    )


def run_host_git_clone(
    *,
    repo_url: str,
    windows_target_path: str,
    github_token: str,
    step: str,
    verbose_sink: Callable[[str], None] | None = None,
) -> None:
    """Clone repository using host git executable with auth fallback."""
    from branchnexus.ui.services.git_operations import looks_like_git_auth_failure

    git_executable = shutil.which("git")
    if not git_executable:
        raise BranchNexusError(
            "Host git executable bulunamadi.",
            code=ExitCode.RUNTIME_ERROR,
            hint="Windows tarafinda git kurulu oldugundan emin olun.",
        )

    def _run_clone_once(token_value: str, step_name: str) -> subprocess.CompletedProcess[str]:
        command = [git_executable]
        if token_value:
            command.extend(["-c", f"http.extraheader=Authorization: Bearer {token_value}"])
        command.extend(["clone", repo_url, windows_target_path])
        run_env = dict(os.environ)
        run_env.setdefault("GIT_TERMINAL_PROMPT", "0")
        run_env.setdefault("GCM_INTERACTIVE", "never")
        run_env.setdefault("GIT_ASKPASS", "echo")
        run_env.setdefault("SSH_ASKPASS", "echo")
        emit_terminal_progress(
            verbose_sink,
            level="RUN",
            step=step_name,
            message=f"command={command_for_log(command)}",
        )
        try:
            return run_with_heartbeat(
                command=command,
                env=run_env,
                timeout_seconds=HOST_GIT_CLONE_TIMEOUT_SECONDS,
                step=step_name,
                verbose_sink=verbose_sink,
            )
        except subprocess.TimeoutExpired as exc:
            emit_terminal_progress(
                verbose_sink,
                level="TIMEOUT",
                step=step_name,
                message=f"timeout={HOST_GIT_CLONE_TIMEOUT_SECONDS}s",
            )
            raise BranchNexusError(
                f"Host git clone zaman asimina ugradi: {step_name}",
                code=ExitCode.RUNTIME_ERROR,
                hint="Host ag/proxy ayarlarini kontrol edin.",
            ) from exc

    token = github_token.strip()
    result = _run_clone_once(token, step)
    if result.returncode == 0:
        emit_terminal_progress(verbose_sink, level="OK", step=step, message="host git clone completed")
        return

    details = (result.stderr or result.stdout or "").strip()
    if token and looks_like_git_auth_failure(details):
        emit_terminal_progress(
            verbose_sink,
            level="WARN",
            step=step,
            message="host auth failed, retrying clone without token",
        )
        retry_step = f"{step}:no-auth"
        retry_result = _run_clone_once("", retry_step)
        if retry_result.returncode == 0:
            emit_terminal_progress(
                verbose_sink,
                level="OK",
                step=retry_step,
                message="host git clone completed without token",
            )
            return
        details = (retry_result.stderr or retry_result.stdout or "").strip()

    raise BranchNexusError(
        f"Host git clone basarisiz: {step}",
        code=ExitCode.RUNTIME_ERROR,
        hint=details or "Host git clone loglarini kontrol edin.",
    )


def clone_via_host_git(
    *,
    distribution: str,
    repo_url: str,
    anchor_path: str,
    repo_key: str,
    github_token: str,
    verbose_sink: Callable[[str], None] | None = None,
) -> None:
    """Clone by converting WSL path to Windows target and using host git."""
    windows_target = windows_to_wsl_path(
        distribution=distribution,
        wsl_path=anchor_path,
    )
    run_host_git_clone(
        repo_url=repo_url,
        windows_target_path=windows_target,
        github_token=github_token,
        step=f"repo-clone:{repo_key}:host-bridge",
        verbose_sink=verbose_sink,
    )


# Backward compatibility aliases during app.py extraction.
_github_repo_full_name_from_url = parse_github_repo
_ensure_wsl_gh_cli = ensure_wsl_gh
_try_clone_remote_repo_with_wsl_gh = clone_via_wsl_gh
_resolve_windows_path_for_wsl = windows_to_wsl_path
_run_host_git_clone = run_host_git_clone
_clone_remote_repo_via_host_git = clone_via_host_git
_looks_like_gh_auth_failure = looks_like_gh_auth_failure
