"""WSL runtime preflight: prepare pane paths, repos, and worktrees."""

from __future__ import annotations

import hashlib
import logging as py_logging
import os
from collections.abc import Callable
from pathlib import Path

from branchnexus.errors import BranchNexusError
from branchnexus.git.remote_workspace import repo_name_from_url
from branchnexus.ui.runtime.constants import WSL_FETCH_DRY_RUN_TIMEOUT_SECONDS
from branchnexus.ui.runtime.runtime_progress import emit_terminal_progress
from branchnexus.ui.services.github_env import github_token_env
from branchnexus.ui.services.git_operations import (
    clone_with_fallback,
    is_legacy_worktree_path,
    normalize_branch_pair,
    parse_worktree_map,
    parse_worktree_paths,
    run_wsl_git_command,
)
from branchnexus.ui.services.security import truncate_log
from branchnexus.ui.services.session_manager import (
    _resolve_runtime_workspace_root_wsl,
)
from branchnexus.ui.services.wsl_runner import run_wsl_probe_script, run_wsl_script

logger = py_logging.getLogger(__name__)


def _shorten_segment(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    head_length = max(1, max_length - 9)
    head = value[:head_length].rstrip("-.")
    if not head:
        head = value[:head_length]
    return f"{head}-{digest}"


def _sanitize_repo_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value.strip())
    cleaned = cleaned.strip("-.")
    segment = cleaned or "repo"
    return _shorten_segment(segment, max_length=28)


def _workspace_root_expression(workspace_root_wsl: str) -> str:
    root = workspace_root_wsl.strip()
    if root.startswith("/"):
        return root
    return "$HOME/branchnexus-workspace"


def select_runtime_wsl_distribution(
    available_distributions: list[str],
    *,
    configured: str = "",
    current: str = "",
) -> str:
    available = [item.strip() for item in available_distributions if item.strip()]
    if not available:
        return ""
    if current.strip() in set(available):
        return current.strip()
    if configured.strip() in set(available):
        return configured.strip()
    return available[0]


def _resolve_wsl_target_path(repo_path: str, *, workspace_root: str, pane_index: int) -> str:
    repo_value = repo_path.strip()
    if "://" in repo_value or repo_value.startswith("git@"):
        try:
            repo_dir = _sanitize_repo_segment(repo_name_from_url(repo_value))
        except BranchNexusError:
            repo_dir = _sanitize_repo_segment(Path(repo_value).name or "repo")
        return f"{workspace_root}/.bnx/w/{repo_dir}/p{pane_index + 1}"
    return repo_value


def _sanitize_branch_segment(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in value.strip())
    cleaned = cleaned.strip("-.")
    segment = cleaned or "branch"
    return _shorten_segment(segment, max_length=32)


def prepare_wsl_runtime_pane_paths(
    *,
    distribution: str,
    repo_branch_pairs: list[tuple[str, str]],
    workspace_root_wsl: str,
    github_token: str = "",
    progress: Callable[[str, str], None] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> list[str]:
    if not repo_branch_pairs:
        return []

    def emit(step: str, message: str) -> None:
        if progress is not None:
            progress(step, message)

    def emit_verbose(level: str, step: str, message: str) -> None:
        emit_terminal_progress(verbose_sink, level=level, step=step, message=message)

    workspace_root = _resolve_runtime_workspace_root_wsl(distribution, workspace_root_wsl)
    runtime_root = f"{workspace_root.rstrip('/')}/.bnx"
    repos_root = workspace_root.rstrip("/")
    worktrees_root = f"{runtime_root}/w"
    run_env = dict(os.environ)
    run_env.setdefault("GIT_TERMINAL_PROMPT", "0")
    run_env.setdefault("GCM_INTERACTIVE", "never")
    run_env.setdefault("GIT_ASKPASS", "echo")
    run_env.setdefault("SSH_ASKPASS", "echo")
    if github_token.strip():
        run_env.update(github_token_env(github_token))

    logger.info(
        "runtime-open preflight-start distribution=%s workspace_root=%s pair_count=%s",
        distribution,
        workspace_root,
        len(repo_branch_pairs),
    )
    emit_verbose(
        "INFO",
        "preflight-start",
        f"workspace={workspace_root} pane_count={len(repo_branch_pairs)}",
    )
    emit("preflight-start", f"WSL hazirlik basladi ({len(repo_branch_pairs)} panel).")
    emit("init-runtime-dirs", "Runtime dizinleri hazirlaniyor...")
    run_wsl_script(
        distribution=distribution,
        script=f'mkdir -p "{repos_root}" "{worktrees_root}"',
        step="init-runtime-dirs",
        env=run_env,
        verbose_sink=verbose_sink,
    )

    repo_state: dict[str, tuple[str, str]] = {}
    worktree_map_by_anchor: dict[str, dict[str, str]] = {}
    worktree_paths_by_anchor: dict[str, set[str]] = {}

    for repo_path, _ in repo_branch_pairs:
        repo_value = repo_path.strip()
        if not repo_value or repo_value in repo_state:
            continue
        emit("repo-check", f"Depo kontrol ediliyor: {repo_value}")

        if "://" in repo_value or repo_value.startswith("git@"):
            repo_key = _sanitize_repo_segment(repo_name_from_url(repo_value))
            anchor_path = f"{repos_root}/{repo_key}"
            check = run_wsl_probe_script(
                distribution=distribution,
                script=(f'git -C "{anchor_path}" rev-parse --is-inside-work-tree >/dev/null 2>&1'),
                step=f"repo-presence:{repo_key}",
                env=run_env,
                verbose_sink=verbose_sink,
            )
            logger.debug(
                "runtime-open repo-check repo=%s anchor=%s exists=%s",
                repo_value,
                anchor_path,
                check.returncode == 0,
            )
            if check.returncode == 0:
                try:
                    dry_fetch = run_wsl_probe_script(
                        distribution=distribution,
                        script=f'git -C "{anchor_path}" fetch --dry-run --prune 2>&1',
                        step=f"repo-fetch-dry-run:{repo_key}",
                        timeout_seconds=WSL_FETCH_DRY_RUN_TIMEOUT_SECONDS,
                        env=run_env,
                        verbose_sink=verbose_sink,
                    )
                    fetch_preview = (dry_fetch.stdout + "\n" + dry_fetch.stderr).strip()
                    if dry_fetch.returncode != 0:
                        logger.warning(
                            "runtime-open repo-fetch-check-failed repo=%s code=%s output=%s",
                            repo_value,
                            dry_fetch.returncode,
                            truncate_log(fetch_preview, limit=220),
                        )
                        emit(
                            "repo-fetch-skip",
                            (
                                "Depo degisiklik kontrolu yapilamadi, mevcut kopya kullaniliyor: "
                                f"{repo_value}"
                            ),
                        )
                        emit_verbose(
                            "WARN",
                            f"repo-fetch-skip:{repo_key}",
                            truncate_log(fetch_preview, limit=220) or "dry-run fetch failed",
                        )
                    elif fetch_preview:
                        logger.info(
                            "runtime-open repo-update-detected repo=%s preview=%s",
                            repo_value,
                            truncate_log(fetch_preview, limit=220),
                        )
                        emit("repo-fetch", f"Depo guncelleniyor (fetch): {repo_value}")
                        run_wsl_git_command(
                            distribution=distribution,
                            git_args=["-C", anchor_path, "fetch", "--prune", "--tags"],
                            step=f"repo-fetch:{repo_key}",
                            env=run_env,
                            github_token=github_token,
                            fallback_without_auth=True,
                            verbose_sink=verbose_sink,
                        )
                    else:
                        logger.info("runtime-open repo-up-to-date repo=%s", repo_value)
                        emit("repo-up-to-date", f"Depo guncel: {repo_value}")
                        emit_verbose(
                            "INFO",
                            f"repo-up-to-date:{repo_key}",
                            "dry-run fetch did not report changes",
                        )
                except BranchNexusError as exc:
                    details = (exc.hint or exc.message).strip()
                    logger.warning(
                        "runtime-open repo-fetch-check-error repo=%s error=%s",
                        repo_value,
                        truncate_log(details, limit=220),
                    )
                    emit(
                        "repo-fetch-skip",
                        (
                            "Depo degisiklik kontrolu zamaninda tamamlanamadi, mevcut kopya kullaniliyor: "
                            f"{repo_value}"
                        ),
                    )
                    emit_verbose(
                        "WARN",
                        f"repo-fetch-skip:{repo_key}",
                        truncate_log(details, limit=220) or "dry-run fetch timeout",
                    )
            else:
                emit("repo-clone", f"Depo klonlaniyor: {repo_value}")
                clone_with_fallback(
                    distribution=distribution,
                    repo_url=repo_value,
                    anchor_path=anchor_path,
                    repo_key=repo_key,
                    env=run_env,
                    github_token=github_token,
                    verbose_sink=verbose_sink,
                )
                logger.info("runtime-open repo-cloned repo=%s anchor=%s", repo_value, anchor_path)

            run_wsl_script(
                distribution=distribution,
                script=(f'git -C "{anchor_path}" rev-parse --is-inside-work-tree >/dev/null 2>&1'),
                step=f"repo-verify:{repo_key}",
                env=run_env,
                verbose_sink=verbose_sink,
            )
        else:
            anchor_path = repo_value
            repo_key = _sanitize_repo_segment(Path(repo_value).name or "repo")
            run_wsl_script(
                distribution=distribution,
                script=f'test -d "{anchor_path}/.git"',
                step=f"repo-local-check:{repo_key}",
                env=run_env,
                verbose_sink=verbose_sink,
            )
            has_origin = run_wsl_probe_script(
                distribution=distribution,
                script=f'git -C "{anchor_path}" remote get-url origin >/dev/null 2>&1',
                step=f"repo-origin-check:{repo_key}",
                env=run_env,
                verbose_sink=verbose_sink,
            )
            if has_origin.returncode == 0:
                try:
                    dry_fetch = run_wsl_probe_script(
                        distribution=distribution,
                        script=f'git -C "{anchor_path}" fetch --dry-run --prune 2>&1',
                        step=f"repo-fetch-dry-run:{repo_key}",
                        timeout_seconds=WSL_FETCH_DRY_RUN_TIMEOUT_SECONDS,
                        env=run_env,
                        verbose_sink=verbose_sink,
                    )
                    fetch_preview = (dry_fetch.stdout + "\n" + dry_fetch.stderr).strip()
                    if dry_fetch.returncode != 0:
                        logger.warning(
                            "runtime-open repo-fetch-check-failed repo=%s code=%s output=%s",
                            repo_value,
                            dry_fetch.returncode,
                            truncate_log(fetch_preview, limit=220),
                        )
                        emit(
                            "repo-fetch-skip",
                            (
                                "Depo degisiklik kontrolu yapilamadi, mevcut kopya kullaniliyor: "
                                f"{repo_value}"
                            ),
                        )
                        emit_verbose(
                            "WARN",
                            f"repo-fetch-skip:{repo_key}",
                            truncate_log(fetch_preview, limit=220) or "dry-run fetch failed",
                        )
                    elif fetch_preview:
                        logger.info(
                            "runtime-open repo-update-detected repo=%s preview=%s",
                            repo_value,
                            truncate_log(fetch_preview, limit=220),
                        )
                        emit("repo-fetch", f"Depo guncelleniyor (fetch): {repo_value}")
                        run_wsl_git_command(
                            distribution=distribution,
                            git_args=["-C", anchor_path, "fetch", "--prune", "--tags"],
                            step=f"repo-fetch:{repo_key}",
                            env=run_env,
                            github_token=github_token,
                            fallback_without_auth=True,
                            verbose_sink=verbose_sink,
                        )
                    else:
                        logger.info("runtime-open repo-up-to-date repo=%s", repo_value)
                        emit("repo-up-to-date", f"Depo guncel: {repo_value}")
                        emit_verbose(
                            "INFO",
                            f"repo-up-to-date:{repo_key}",
                            "dry-run fetch did not report changes",
                        )
                except BranchNexusError as exc:
                    details = (exc.hint or exc.message).strip()
                    logger.warning(
                        "runtime-open repo-fetch-check-error repo=%s error=%s",
                        repo_value,
                        truncate_log(details, limit=220),
                    )
                    emit(
                        "repo-fetch-skip",
                        (
                            "Depo degisiklik kontrolu zamaninda tamamlanamadi, mevcut kopya kullaniliyor: "
                            f"{repo_value}"
                        ),
                    )
                    emit_verbose(
                        "WARN",
                        f"repo-fetch-skip:{repo_key}",
                        truncate_log(details, limit=220) or "dry-run fetch timeout",
                    )
            else:
                logger.info("runtime-open repo-no-origin repo=%s path=%s", repo_value, anchor_path)
                emit("repo-no-origin", f"Depo uzak origin icermiyor: {repo_value}")
                emit_verbose("WARN", f"repo-no-origin:{repo_key}", f"path={anchor_path}")
            run_wsl_script(
                distribution=distribution,
                script=f'test -d "{anchor_path}/.git"',
                step=f"repo-verify:{repo_key}",
                env=run_env,
                verbose_sink=verbose_sink,
            )

        repo_state[repo_value] = (anchor_path, repo_key)

        emit("worktree-list", f"Worktree listesi okunuyor: {repo_value}")
        worktree_list = run_wsl_script(
            distribution=distribution,
            script=f'git -C "{anchor_path}" worktree list --porcelain',
            step=f"worktree-list:{repo_key}",
            env=run_env,
            verbose_sink=verbose_sink,
        ).stdout
        worktree_map_by_anchor[anchor_path] = parse_worktree_map(worktree_list)
        worktree_paths_by_anchor[anchor_path] = parse_worktree_paths(worktree_list)

    pane_paths: list[str] = []
    for pane_index, (repo_path, branch) in enumerate(repo_branch_pairs):
        repo_value = repo_path.strip()
        if not repo_value:
            continue
        local_branch, remote_branch = normalize_branch_pair(branch)
        if not local_branch or not remote_branch:
            continue

        anchor_path, repo_key = repo_state[repo_value]
        emit("branch-ensure", f"Panel {pane_index + 1}: branch hazirlaniyor ({local_branch})")
        run_wsl_script(
            distribution=distribution,
            script=(
                f'if git -C "{anchor_path}" show-ref --verify --quiet "refs/heads/{local_branch}"; then '
                "true; "
                f'elif git -C "{anchor_path}" show-ref --verify --quiet "refs/remotes/{remote_branch}"; then '
                f'git -C "{anchor_path}" branch "{local_branch}" "{remote_branch}"; '
                "else exit 13; fi"
            ),
            step=f"branch-ensure:p{pane_index + 1}",
            env=run_env,
            verbose_sink=verbose_sink,
        )

        branch_map = worktree_map_by_anchor.setdefault(anchor_path, {})
        known_paths = worktree_paths_by_anchor.setdefault(anchor_path, set())
        branch_key = _sanitize_branch_segment(local_branch)
        pane_path = f"{worktrees_root}/{repo_key}/p{pane_index + 1}-{branch_key}"
        existing_path = branch_map.get(local_branch, "").strip()
        if existing_path and is_legacy_worktree_path(
            existing_path, workspace_root=workspace_root
        ):
            logger.info(
                "runtime-open worktree-migrate pane=%s branch=%s old_path=%s",
                pane_index + 1,
                local_branch,
                existing_path,
            )
            run_wsl_script(
                distribution=distribution,
                script=(
                    f'if [ -d "{existing_path}" ]; then '
                    f'git -C "{anchor_path}" worktree remove --force "{existing_path}" >/dev/null 2>&1 || '
                    f'rm -rf "{existing_path}" ; fi'
                ),
                step=f"worktree-migrate-remove:p{pane_index + 1}",
                env=run_env,
                verbose_sink=verbose_sink,
            )
            branch_map.pop(local_branch, None)
            known_paths.discard(existing_path)
            existing_path = ""
        if pane_path in known_paths:
            emit("worktree-reuse", f"Panel {pane_index + 1}: mevcut worktree kullaniliyor")
            logger.info(
                "runtime-open worktree-reuse pane=%s repo=%s branch=%s path=%s",
                pane_index + 1,
                repo_value,
                local_branch,
                pane_path,
            )
        else:
            emit("worktree-add", f"Panel {pane_index + 1}: worktree olusturuluyor")
            run_wsl_script(
                distribution=distribution,
                script=(
                    f'rm -rf "{pane_path}" ; mkdir -p "{worktrees_root}/{repo_key}" ; '
                    f'git -C "{anchor_path}" worktree add --force "{pane_path}" "{local_branch}"'
                ),
                step=f"worktree-add:p{pane_index + 1}",
                env=run_env,
                verbose_sink=verbose_sink,
            )
            known_paths.add(pane_path)
            logger.info(
                "runtime-open worktree-created pane=%s repo=%s branch=%s path=%s",
                pane_index + 1,
                repo_value,
                local_branch,
                pane_path,
            )

        emit("branch-ff", f"Panel {pane_index + 1}: remote ile hizalaniyor")
        run_wsl_script(
            distribution=distribution,
            script=(
                f'if git -C "{pane_path}" show-ref --verify --quiet "refs/remotes/{remote_branch}"; then '
                f'git -C "{pane_path}" merge --ff-only "{remote_branch}" >/dev/null 2>&1; '
                "fi"
            ),
            step=f"branch-ff:p{pane_index + 1}",
            env=run_env,
            verbose_sink=verbose_sink,
        )
        pane_paths.append(pane_path)

    logger.info("runtime-open preflight-complete pane_paths=%s", len(pane_paths))
    emit_verbose("INFO", "preflight-complete", f"pane_paths={len(pane_paths)}")
    emit("preflight-complete", f"WSL hazirlik tamamlandi ({len(pane_paths)} panel).")
    return pane_paths
