"""GUI shell and runtime dashboard orchestration flow."""

from __future__ import annotations

import hashlib
import logging as py_logging
import os
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, field_validator

from branchnexus.config import (
    AppConfig,
    load_config,
    save_config,
)
from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.git.github_repositories import (
    GitHubRepository,
    list_github_repositories,
    list_github_repository_branches,
)
from branchnexus.git.remote_workspace import (
    ensure_remote_repo_synced,
    list_remote_branches_in_repo,
    repo_name_from_url,
    resolve_wsl_home_directory,
)
from branchnexus.orchestrator import OrchestrationRequest
from branchnexus.presets import resolve_terminal_template
from branchnexus.runtime.wsl_discovery import build_wsl_command, list_distributions, to_wsl_path
from branchnexus.session import build_runtime_snapshot, parse_runtime_snapshot
from branchnexus.terminal import RuntimeKind, TerminalService
from branchnexus.tmux.bootstrap import ensure_tmux
from branchnexus.ui.screens.runtime_dashboard import RuntimeDashboardScreen
from branchnexus.ui.services.git_operations import (
    _clone_remote_repo_with_fallback,
    _is_legacy_runtime_worktree_path,
    _normalize_branch_pair,
    _parse_worktree_branch_map,
    _parse_worktree_paths,
    _run_wsl_git_command,
)
from branchnexus.ui.services.github_service import (
    _github_repo_full_name_from_url,
)
from branchnexus.ui.services.security import (
    command_for_log as _command_for_log,
)
from branchnexus.ui.services.security import (
    sanitize_terminal_log_text as _sanitize_terminal_log_text,
)
from branchnexus.ui.services.security import (
    truncate_log as _truncate_log_text,
)
from branchnexus.ui.services.session_manager import (
    _resolve_runtime_workspace_root_wsl,
    _run_fresh_start_reset,
)
from branchnexus.ui.services.windows_terminal import (
    _apply_windows_terminal_profile_font_size,
)
from branchnexus.ui.services.wsl_runner import (
    background_subprocess_kwargs as _background_subprocess_kwargs,
)
from branchnexus.ui.services.wsl_runner import (
    run_with_heartbeat as _run_subprocess_with_heartbeat,
)
from branchnexus.ui.services.wsl_runner import (
    run_wsl_probe_script as _run_wsl_probe_script,
)
from branchnexus.ui.widgets.runtime_output import RuntimeOutputPanel
from branchnexus.worktree.manager import WorktreeAssignment

from ..state import AppState

logger = py_logging.getLogger(__name__)
_WSL_PREFLIGHT_TIMEOUT_SECONDS = 300
_WSL_GIT_TIMEOUT_SECONDS = 300
_WSL_PROGRESS_LOG_IO_TIMEOUT_SECONDS = 15
_TERMINAL_LOG_TRUNCATE_LIMIT = 320
_DEFAULT_WSL_PROGRESS_LOG_PATH = "/tmp/branchnexus-open-progress.log"  # nosec B108
_COMMAND_HEARTBEAT_SECONDS = 10
_WSL_GIT_PROBE_TIMEOUT_SECONDS = 30
_WSL_FETCH_DRY_RUN_TIMEOUT_SECONDS = 15
_WSL_GIT_CLONE_PARTIAL_TIMEOUT_SECONDS = 180
_WSL_GIT_CLONE_FULL_TIMEOUT_SECONDS = 300
_HOST_GIT_CLONE_TIMEOUT_SECONDS = 90
_WSL_GH_CLONE_TIMEOUT_SECONDS = 240
_AUTH_BEARER_PATTERN = re.compile(r"(Authorization:\s*Bearer)\s+\S+", re.IGNORECASE)
_URL_CREDENTIAL_PATTERN = re.compile(r"(https?://)([^/\s:@]+):([^@\s]+)@")
_GH_TOKEN_PATTERN = re.compile(r"\bgh[pousr]_[A-Za-z0-9]+\b")
_GITHUB_HTTPS_REPO_PATTERN = re.compile(
    r"^https?://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)
_GITHUB_SSH_REPO_PATTERN = re.compile(
    r"^git@github\.com:([^/\s]+)/([^/\s]+?)(?:\.git)?$", re.IGNORECASE
)


@dataclass
class Toast:
    level: str
    message: str


class WizardRouter:
    def __init__(self) -> None:
        self.steps: list[str] = []
        self.index = 0

    def configure(self, steps: list[str]) -> None:
        self.steps = steps
        self.index = 0

    def current(self) -> str | None:
        if not self.steps:
            return None
        return self.steps[self.index]

    def next(self) -> str | None:
        if self.index < len(self.steps) - 1:
            self.index += 1
        return self.current()

    def prev(self) -> str | None:
        if self.index > 0:
            self.index -= 1
        return self.current()


class AppShell:
    def __init__(
        self, state: AppState | None = None, *, route_steps: list[str] | None = None
    ) -> None:
        self.state = state or AppState()
        self.router = WizardRouter()
        self.router.configure(route_steps or ["runtime"])
        self.toast: Toast | None = None
        self.closed = False
        self._close_guard: Callable[[], bool] | None = None

    def show_toast(self, message: str, level: str = "INFO") -> None:
        self.toast = Toast(level=level, message=message)

    def set_close_guard(self, guard: Callable[[], bool]) -> None:
        self._close_guard = guard

    def close(self, *, allow: bool = True) -> bool:
        if not allow:
            return False
        if self._close_guard and not self._close_guard():
            return False
        self.closed = True
        return True


class WizardSelections(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    root_path: str
    repo_url: str
    repo_path_wsl: str
    layout: str
    panes: int
    cleanup: str
    wsl_distribution: str
    tmux_auto_install: bool
    assignments: dict[int, tuple[str, str]]
    github_token: str = ""

    @field_validator(
        "root_path", "repo_url", "repo_path_wsl", "layout", "cleanup", "wsl_distribution"
    )
    @classmethod
    def _normalize_str_fields(cls, value: str) -> str:
        return value.strip()

    @field_validator("panes", mode="before")
    @classmethod
    def _coerce_panes(cls, value: object) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0


def build_state_from_config(config: AppConfig) -> AppState:
    template_count = resolve_terminal_template(
        config.default_panes, custom_value=config.default_panes
    )
    return AppState(
        root_path=config.default_root,
        remote_repo_url=config.remote_repo_url,
        layout=config.default_layout,
        panes=config.default_panes,
        cleanup=config.cleanup_policy,
        wsl_distribution=config.wsl_distribution,
        runtime_profile=config.runtime_profile,
        terminal_template=template_count,
        max_terminals=config.terminal_max_count,
        terminal_default_runtime=config.terminal_default_runtime,
    )


def apply_wizard_selections(
    *,
    config: AppConfig,
    state: AppState,
    selections: WizardSelections,
) -> None:
    state.root_path = selections.root_path
    state.remote_repo_url = selections.repo_url
    state.layout = selections.layout
    state.panes = selections.panes
    state.cleanup = selections.cleanup
    state.wsl_distribution = selections.wsl_distribution
    state.assignments = dict(selections.assignments)

    config.default_root = selections.root_path
    config.remote_repo_url = selections.repo_url
    config.github_token = selections.github_token
    config.default_layout = selections.layout
    config.default_panes = selections.panes
    config.cleanup_policy = selections.cleanup
    config.wsl_distribution = selections.wsl_distribution
    config.tmux_auto_install = selections.tmux_auto_install


def selection_errors(selections: WizardSelections) -> list[str]:
    errors: list[str] = []
    if not selections.repo_url.strip():
        errors.append("GitHub repo secimi zorunludur.")
    if selections.layout not in {"horizontal", "vertical", "grid"}:
        errors.append("Layout gecersiz.")
    if selections.panes < 2 or selections.panes > 6:
        errors.append("Pane sayisi 2-6 araliginda olmalidir.")
    if selections.cleanup not in {"session", "persistent"}:
        errors.append("Cleanup policy gecersiz.")
    if not selections.wsl_distribution.strip():
        errors.append("WSL dagitimi secilmelidir.")
    if len(selections.assignments) != selections.panes:
        errors.append("Her panel icin remote branch secimi tamamlanmalidir.")

    for pane, selection in sorted(selections.assignments.items()):
        repo_path, branch = selection
        if not repo_path.strip():
            errors.append(f"Pane {pane} icin repo secimi zorunludur.")
        if not branch.strip():
            errors.append(f"Pane {pane} icin branch secimi zorunludur.")

    return errors


def build_orchestration_request(
    selections: WizardSelections,
    available_distributions: list[str],
    *,
    path_converter: Callable[[str, str], str] | None = None,
    home_resolver: Callable[..., str | PurePosixPath] | None = None,
    repo_sync: Callable[..., PurePosixPath] | None = None,
    branch_loader: Callable[..., list[str]] | None = None,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> OrchestrationRequest:
    distribution = selections.wsl_distribution
    logger.debug(
        "Building orchestration request distribution=%s panes=%s layout=%s",
        distribution,
        selections.panes,
        selections.layout,
    )
    convert = path_converter or (
        lambda distro, host_path: to_wsl_path(distro, host_path, runner=runner)
    )
    resolve_home = home_resolver or resolve_wsl_home_directory
    sync_repo = repo_sync or ensure_remote_repo_synced
    load_branches = branch_loader or list_remote_branches_in_repo

    if selections.root_path.strip():
        workspace_root_wsl = convert(distribution, selections.root_path)
    else:
        workspace_root_wsl = str(resolve_home(distribution=distribution, runner=runner))
        logger.debug("Workspace root empty; using WSL home directory=%s", workspace_root_wsl)

    fallback_repo_path_wsl = selections.repo_path_wsl.strip()
    if not fallback_repo_path_wsl and selections.repo_url.strip():
        fallback_repo_path_wsl = str(
            sync_repo(
                distribution=distribution,
                repo_url=selections.repo_url,
                workspace_root_wsl=workspace_root_wsl,
                runner=runner,
            )
        )

    assignments: list[WorktreeAssignment] = []
    available_remote_by_repo: dict[str, set[str]] = {}
    for pane in sorted(selections.assignments):
        repo_path_wsl, remote_branch = selections.assignments[pane]
        selected_repo_path = repo_path_wsl.strip() or fallback_repo_path_wsl
        if not selected_repo_path:
            logger.error("Selected repository missing pane=%s", pane)
            raise BranchNexusError(
                f"Pane {pane} icin repository secimi bulunamadi.",
                code=ExitCode.VALIDATION_ERROR,
                hint="Panel repo secimini tekrar yapin.",
            )

        if selected_repo_path not in available_remote_by_repo:
            available_remote_by_repo[selected_repo_path] = set(
                load_branches(
                    distribution=distribution,
                    repo_path_wsl=selected_repo_path,
                    runner=runner,
                )
            )

        if remote_branch not in available_remote_by_repo[selected_repo_path]:
            logger.error("Selected remote branch missing pane=%s branch=%s", pane, remote_branch)
            raise BranchNexusError(
                f"Remote branch bulunamadi: {remote_branch}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Branch listesini yenileyip tekrar secin.",
            )
        assignments.append(
            WorktreeAssignment(
                pane=pane,
                repo_path=PurePosixPath(selected_repo_path),
                branch=remote_branch,
            )
        )

    return OrchestrationRequest(
        distribution=distribution,
        available_distributions=available_distributions,
        layout=selections.layout,
        cleanup_policy=selections.cleanup,
        assignments=assignments,
        worktree_base=PurePosixPath(workspace_root_wsl) / ".branchnexus-worktrees",
        tmux_auto_install=selections.tmux_auto_install,
    )


def format_runtime_events(panel: RuntimeOutputPanel) -> str:
    lines = [f"[{event.state}] {event.step}: {event.message}" for event in panel.events]
    return "\n".join(lines).strip()


def tmux_shortcuts_lines(distribution: str, session_name: str) -> list[str]:
    attach_cmd = f"wsl -d {distribution} -- tmux attach-session -t {session_name}"
    return [
        "Kisayollar:",
        "- Prefix: Ctrl+b",
        "- Mouse ile panel gecis: pane uzerine tikla",
        "- Yazi boyutu: Ctrl + Mouse Wheel (Windows Terminal)",
        "- Alternatif zoom: Ctrl + '+' / Ctrl + '-'",
        "- Panel gecis: Prefix + Ok tuslari",
        "- Panel kapat: Prefix + x",
        "- Oturumdan ayril: Prefix + d",
        f"- Yeniden baglan: {attach_cmd}",
        f"- Zoom calismazsa Windows Terminal ile ac: wt.exe -w new {attach_cmd}",
    ]


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _format_terminal_progress_line(level: str, step: str, message: str) -> str:
    stamp = datetime.now().strftime("%H:%M:%S")
    step_name = step.strip() or "runtime"
    detail = _sanitize_terminal_log_text(message)
    return f"[BranchNexus][{stamp}][{level}] {step_name}: {detail}"


def _emit_terminal_progress(
    sink: Callable[[str], None] | None,
    *,
    level: str,
    step: str,
    message: str,
) -> None:
    if sink is None:
        return
    sink(_format_terminal_progress_line(level, step, message))


def _build_runtime_progress_log_path(workspace_root_wsl: str) -> str:
    root = workspace_root_wsl.replace("\ufeff", "").replace("\x00", "").strip().rstrip("/")
    if not root.startswith("/"):
        return ""
    return f"{root}/.bnx/runtime/open-progress.log"


def _init_wsl_progress_log(
    *,
    distribution: str,
    log_path: str,
    env: dict[str, str] | None = None,
) -> None:
    path = log_path.strip()
    if not path:
        return
    parent = str(PurePosixPath(path).parent)
    command = build_wsl_command(
        distribution,
        ["bash", "-lc", f"mkdir -p {shlex.quote(parent)}; : > {shlex.quote(path)}"],
    )
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=run_env,
            timeout=_WSL_PROGRESS_LOG_IO_TIMEOUT_SECONDS,
            **_background_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.debug("runtime-open progress-log-init failed path=%s", path, exc_info=True)


def _append_wsl_progress_log(
    *,
    distribution: str,
    log_path: str,
    line: str,
    env: dict[str, str] | None = None,
) -> None:
    path = log_path.strip()
    if not path:
        return
    parent = str(PurePosixPath(path).parent)
    text = line.strip()
    if not text:
        return
    command = build_wsl_command(
        distribution,
        [
            "bash",
            "-lc",
            (
                f"mkdir -p {shlex.quote(parent)}; "
                f"touch {shlex.quote(path)}; "
                f'printf "%s\\n" {shlex.quote(text)} >> {shlex.quote(path)}'
            ),
        ],
    )
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    try:
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            env=run_env,
            timeout=_WSL_PROGRESS_LOG_IO_TIMEOUT_SECONDS,
            **_background_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.debug("runtime-open progress-log-append failed path=%s", path, exc_info=True)


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


def _shorten_segment(value: str, *, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    head_length = max(1, max_length - 9)
    head = value[:head_length].rstrip("-.")
    if not head:
        head = value[:head_length]
    return f"{head}-{digest}"


def _run_wsl_script(
    *,
    distribution: str,
    script: str,
    step: str,
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess:
    command = build_wsl_command(distribution, ["bash", "-lc", script])
    logger.debug("runtime-open preflight-run step=%s command=%s", step, _command_for_log(command))
    _emit_terminal_progress(
        verbose_sink,
        level="RUN",
        step=step,
        message=f"command={_command_for_log(command)}",
    )
    try:
        result = _run_subprocess_with_heartbeat(
            command=command,
            env=env,
            timeout_seconds=_WSL_PREFLIGHT_TIMEOUT_SECONDS,
            step=step,
            verbose_sink=verbose_sink,
        )
    except subprocess.TimeoutExpired as exc:
        logger.error(
            "runtime-open preflight-timeout step=%s timeout=%ss",
            step,
            _WSL_PREFLIGHT_TIMEOUT_SECONDS,
        )
        _emit_terminal_progress(
            verbose_sink,
            level="TIMEOUT",
            step=step,
            message=f"timeout={_WSL_PREFLIGHT_TIMEOUT_SECONDS}s",
        )
        raise BranchNexusError(
            f"Runtime WSL hazirlik adimi zaman asimina ugradi: {step}",
            code=ExitCode.RUNTIME_ERROR,
            hint=(
                "Komut beklenenden uzun surdu. "
                "WSL durumunu, ag baglantisini ve git kimlik ayarlarini kontrol edin."
            ),
        ) from exc
    if result.returncode == 0:
        logger.debug(
            "runtime-open preflight-ok step=%s stdout=%s",
            step,
            _truncate_log_text(result.stdout),
        )
        _emit_terminal_progress(verbose_sink, level="OK", step=step, message="command completed")
        return result
    logger.error(
        "runtime-open preflight-fail step=%s code=%s stderr=%s",
        step,
        result.returncode,
        _truncate_log_text(result.stderr),
    )
    _emit_terminal_progress(
        verbose_sink,
        level="FAIL",
        step=step,
        message=f"code={result.returncode} stderr={_truncate_log_text(result.stderr, limit=220)}",
    )
    raise BranchNexusError(
        f"Runtime WSL hazirlik adimi basarisiz: {step}",
        code=ExitCode.RUNTIME_ERROR,
        hint=result.stderr.strip() or "WSL git/tmux komutlarini kontrol edin.",
    )


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
        _emit_terminal_progress(verbose_sink, level=level, step=step, message=message)

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
        token_value = github_token.strip()
        run_env["BRANCHNEXUS_GH_TOKEN"] = token_value
        run_env["GH_TOKEN"] = token_value
        run_env["GITHUB_TOKEN"] = token_value

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
    _run_wsl_script(
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
            check = _run_wsl_probe_script(
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
                    dry_fetch = _run_wsl_probe_script(
                        distribution=distribution,
                        script=f'git -C "{anchor_path}" fetch --dry-run --prune 2>&1',
                        step=f"repo-fetch-dry-run:{repo_key}",
                        timeout_seconds=_WSL_FETCH_DRY_RUN_TIMEOUT_SECONDS,
                        env=run_env,
                        verbose_sink=verbose_sink,
                    )
                    fetch_preview = (dry_fetch.stdout + "\n" + dry_fetch.stderr).strip()
                    if dry_fetch.returncode != 0:
                        logger.warning(
                            "runtime-open repo-fetch-check-failed repo=%s code=%s output=%s",
                            repo_value,
                            dry_fetch.returncode,
                            _truncate_log_text(fetch_preview, limit=220),
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
                            _truncate_log_text(fetch_preview, limit=220) or "dry-run fetch failed",
                        )
                    elif fetch_preview:
                        logger.info(
                            "runtime-open repo-update-detected repo=%s preview=%s",
                            repo_value,
                            _truncate_log_text(fetch_preview, limit=220),
                        )
                        emit("repo-fetch", f"Depo guncelleniyor (fetch): {repo_value}")
                        _run_wsl_git_command(
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
                        _truncate_log_text(details, limit=220),
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
                        _truncate_log_text(details, limit=220) or "dry-run fetch timeout",
                    )
            else:
                emit("repo-clone", f"Depo klonlaniyor: {repo_value}")
                _clone_remote_repo_with_fallback(
                    distribution=distribution,
                    repo_url=repo_value,
                    anchor_path=anchor_path,
                    repo_key=repo_key,
                    env=run_env,
                    github_token=github_token,
                    verbose_sink=verbose_sink,
                )
                logger.info("runtime-open repo-cloned repo=%s anchor=%s", repo_value, anchor_path)

            _run_wsl_script(
                distribution=distribution,
                script=(f'git -C "{anchor_path}" rev-parse --is-inside-work-tree >/dev/null 2>&1'),
                step=f"repo-verify:{repo_key}",
                env=run_env,
                verbose_sink=verbose_sink,
            )
        else:
            anchor_path = repo_value
            repo_key = _sanitize_repo_segment(Path(repo_value).name or "repo")
            _run_wsl_script(
                distribution=distribution,
                script=f'test -d "{anchor_path}/.git"',
                step=f"repo-local-check:{repo_key}",
                env=run_env,
                verbose_sink=verbose_sink,
            )
            has_origin = _run_wsl_probe_script(
                distribution=distribution,
                script=f'git -C "{anchor_path}" remote get-url origin >/dev/null 2>&1',
                step=f"repo-origin-check:{repo_key}",
                env=run_env,
                verbose_sink=verbose_sink,
            )
            if has_origin.returncode == 0:
                try:
                    dry_fetch = _run_wsl_probe_script(
                        distribution=distribution,
                        script=f'git -C "{anchor_path}" fetch --dry-run --prune 2>&1',
                        step=f"repo-fetch-dry-run:{repo_key}",
                        timeout_seconds=_WSL_FETCH_DRY_RUN_TIMEOUT_SECONDS,
                        env=run_env,
                        verbose_sink=verbose_sink,
                    )
                    fetch_preview = (dry_fetch.stdout + "\n" + dry_fetch.stderr).strip()
                    if dry_fetch.returncode != 0:
                        logger.warning(
                            "runtime-open repo-fetch-check-failed repo=%s code=%s output=%s",
                            repo_value,
                            dry_fetch.returncode,
                            _truncate_log_text(fetch_preview, limit=220),
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
                            _truncate_log_text(fetch_preview, limit=220) or "dry-run fetch failed",
                        )
                    elif fetch_preview:
                        logger.info(
                            "runtime-open repo-update-detected repo=%s preview=%s",
                            repo_value,
                            _truncate_log_text(fetch_preview, limit=220),
                        )
                        emit("repo-fetch", f"Depo guncelleniyor (fetch): {repo_value}")
                        _run_wsl_git_command(
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
                        _truncate_log_text(details, limit=220),
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
                        _truncate_log_text(details, limit=220) or "dry-run fetch timeout",
                    )
            else:
                logger.info("runtime-open repo-no-origin repo=%s path=%s", repo_value, anchor_path)
                emit("repo-no-origin", f"Depo uzak origin icermiyor: {repo_value}")
                emit_verbose("WARN", f"repo-no-origin:{repo_key}", f"path={anchor_path}")
            _run_wsl_script(
                distribution=distribution,
                script=f'test -d "{anchor_path}/.git"',
                step=f"repo-verify:{repo_key}",
                env=run_env,
                verbose_sink=verbose_sink,
            )

        repo_state[repo_value] = (anchor_path, repo_key)

        emit("worktree-list", f"Worktree listesi okunuyor: {repo_value}")
        worktree_list = _run_wsl_script(
            distribution=distribution,
            script=f'git -C "{anchor_path}" worktree list --porcelain',
            step=f"worktree-list:{repo_key}",
            env=run_env,
            verbose_sink=verbose_sink,
        ).stdout
        worktree_map_by_anchor[anchor_path] = _parse_worktree_branch_map(worktree_list)
        worktree_paths_by_anchor[anchor_path] = _parse_worktree_paths(worktree_list)

    pane_paths: list[str] = []
    for pane_index, (repo_path, branch) in enumerate(repo_branch_pairs):
        repo_value = repo_path.strip()
        if not repo_value:
            continue
        local_branch, remote_branch = _normalize_branch_pair(branch)
        if not local_branch or not remote_branch:
            continue

        anchor_path, repo_key = repo_state[repo_value]
        emit("branch-ensure", f"Panel {pane_index + 1}: branch hazirlaniyor ({local_branch})")
        _run_wsl_script(
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
        if existing_path and _is_legacy_runtime_worktree_path(
            existing_path, workspace_root=workspace_root
        ):
            logger.info(
                "runtime-open worktree-migrate pane=%s branch=%s old_path=%s",
                pane_index + 1,
                local_branch,
                existing_path,
            )
            _run_wsl_script(
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
            _run_wsl_script(
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
        _run_wsl_script(
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


def _build_wsl_pane_context_command(
    repo_path: str,
    branch: str,
    *,
    workspace_root: str,
    pane_index: int,
) -> str:
    logger.debug(
        "runtime-open pane-context-build pane=%s repo=%s branch=%s workspace_root=%s",
        pane_index + 1,
        repo_path.strip(),
        branch.strip(),
        workspace_root,
    )
    commands: list[str] = []
    repo_value = repo_path.strip()
    if repo_value:
        if "://" in repo_value or repo_value.startswith("git@"):
            repo_dir = _sanitize_repo_segment(repo_name_from_url(repo_value))
            repo_root = f"{workspace_root}/{repo_dir}"
            target = f"{repo_root}/pane-{pane_index + 1}"
            commands.append(f'mkdir -p "{repo_root}"')
            clone_cmd = (
                'if [ -n "${BRANCHNEXUS_GH_TOKEN:-}" ]; then '
                f'git -c http.extraheader="Authorization: Bearer ${{BRANCHNEXUS_GH_TOKEN}}" '
                f'clone {shlex.quote(repo_value)} "{target}"; '
                f'else git clone {shlex.quote(repo_value)} "{target}"; fi'
            )
            fetch_cmd = (
                'if [ -n "${BRANCHNEXUS_GH_TOKEN:-}" ]; then '
                f'git -c http.extraheader="Authorization: Bearer ${{BRANCHNEXUS_GH_TOKEN}}" '
                f'-C "{target}" fetch --prune --tags; '
                f'else git -C "{target}" fetch --prune --tags; fi'
            )
            commands.append(
                f'if [ -d "{target}/.git" ]; then '
                f"{fetch_cmd}; "
                f'else rm -rf "{target}" ; {clone_cmd}; fi'
            )
            commands.append(f'cd "{target}"')
        else:
            commands.append(f"cd {shlex.quote(repo_value)}")

    branch_value = branch.strip()
    if branch_value:
        local_branch = branch_value[7:] if branch_value.startswith("origin/") else branch_value
        local_branch = local_branch.strip()
        if local_branch:
            remote_branch = (
                branch_value if branch_value.startswith("origin/") else f"origin/{local_branch}"
            )
            local_q = shlex.quote(local_branch)
            remote_q = shlex.quote(remote_branch)
            commands.append(
                "(git rev-parse --is-inside-work-tree >/dev/null 2>&1 && "
                f"(git switch {local_q} 2>/dev/null || "
                f"git checkout {local_q} 2>/dev/null || "
                f"git switch -c {local_q} --track {remote_q} 2>/dev/null || "
                f"git checkout -B {local_q} {remote_q} 2>/dev/null || true))"
            )

    if not commands:
        logger.debug("runtime-open pane-context-build pane=%s generated=true-noop", pane_index + 1)
        return "true"
    result = " ; ".join(commands)
    logger.debug(
        "runtime-open pane-context-build pane=%s command=%s",
        pane_index + 1,
        _truncate_log_text(result),
    )
    return result


def _runtime_interactive_shell_entry() -> str:
    # Keep prompt short so rapid tmux resize redraws do not smear long working paths.
    return "touch ~/.hushlogin >/dev/null 2>&1 || true ; export PROMPT_DIRTRIM=1 ; exec bash -i"


def _build_wsl_pane_startup_command(
    repo_path: str,
    branch: str,
    *,
    workspace_root: str,
    pane_index: int,
) -> str:
    shell_entry = _runtime_interactive_shell_entry()
    pane_script = _build_wsl_pane_context_command(
        repo_path,
        branch,
        workspace_root=workspace_root,
        pane_index=pane_index,
    )
    startup = f"bash -lc {shlex.quote(pane_script + ' ; ' + shell_entry)}"
    logger.debug(
        "runtime-open pane-startup-build pane=%s startup=%s",
        pane_index + 1,
        _truncate_log_text(startup),
    )
    return startup


def _resolve_runtime_grid_dimensions(
    *,
    pane_count: int,
    layout_rows: int | None = None,
    layout_cols: int | None = None,
) -> tuple[int, int]:
    count = max(1, int(pane_count))
    rows = max(1, int(layout_rows or 0))
    cols = max(1, int(layout_cols or 0))

    if rows * cols == count:
        return rows, cols
    if rows == 1:
        return 1, count
    if cols == 1:
        return count, 1

    rows = min(rows, count)
    cols = max(1, (count + rows - 1) // rows)
    if rows * cols < count:
        rows = (count + cols - 1) // cols
    return rows, cols


def _tmux_layout_name_for_grid(rows: int, cols: int) -> str:
    if rows <= 1:
        return "even-horizontal"
    if cols <= 1:
        return "even-vertical"
    return "tiled"


def _runtime_tmux_style_commands(session_name: str) -> list[str]:
    return [
        f"tmux set-option -t {session_name} mouse on",
        "tmux bind-key -n WheelUpPane send-keys -M",
        "tmux bind-key -n WheelDownPane send-keys -M",
        f"tmux set-option -t {session_name} remain-on-exit on",
        f"tmux set-option -t {session_name} status-position bottom",
        f"tmux set-option -t {session_name} status-style bg=colour236,fg=colour252",
        f"tmux set-option -t {session_name} message-style bg=colour31,fg=colour255",
        f"tmux set-option -t {session_name} pane-border-style fg=colour238",
        f"tmux set-option -t {session_name} pane-active-border-style fg=colour45",
        f"tmux set-option -t {session_name} window-status-style fg=colour248,bg=default",
        f"tmux set-option -t {session_name} window-status-current-style fg=colour231,bg=colour31,bold",
        f"tmux set-option -t {session_name} status-left-length 32",
        f"tmux set-option -t {session_name} status-right-length 48",
        f"tmux set-option -t {session_name} status-left {shlex.quote(' #[bold]BranchNexus #[default]#S ')}",
        f"tmux set-option -t {session_name} status-right {shlex.quote('#(whoami)@#H  %H:%M %d-%b-%y ')}",
    ]


def _runtime_tmux_resize_hook_commands(session_name: str, layout_name: str) -> list[str]:
    resize_command = f"select-layout -t {session_name}:0 {layout_name}"
    return [
        f"tmux set-hook -t {session_name} client-resized {shlex.quote(resize_command)}",
    ]


def build_runtime_wsl_bootstrap_command(
    *,
    pane_count: int = 1,
    repo_branch_pairs: list[tuple[str, str]] | None = None,
    workspace_root_wsl: str = "",
    layout_rows: int | None = None,
    layout_cols: int | None = None,
    session_name: str = "branchnexus-runtime",
) -> str:
    requested_pairs = repo_branch_pairs or []
    pairs: list[tuple[str, str]] = [
        (repo.strip(), branch.strip()) for repo, branch in requested_pairs
    ]
    if not pairs:
        pairs = [("", "")]
    workspace_root = _workspace_root_expression(workspace_root_wsl)

    split_count = max(1, int(pane_count), len(pairs))
    lines: list[str] = [
        "tmux start-server",
        (
            'if [ -n "${BRANCHNEXUS_GH_TOKEN:-}" ]; then '
            'tmux set-environment -g BRANCHNEXUS_GH_TOKEN "${BRANCHNEXUS_GH_TOKEN}"; '
            'tmux set-environment -g GH_TOKEN "${BRANCHNEXUS_GH_TOKEN}"; '
            'tmux set-environment -g GITHUB_TOKEN "${BRANCHNEXUS_GH_TOKEN}"; '
            "else tmux set-environment -gu BRANCHNEXUS_GH_TOKEN; "
            "tmux set-environment -gu GH_TOKEN; "
            "tmux set-environment -gu GITHUB_TOKEN; fi"
        ),
        f"tmux kill-session -t {session_name} 2>/dev/null || true",
    ]

    startup_commands = [
        _build_wsl_pane_startup_command(
            repo_path,
            branch,
            workspace_root=workspace_root,
            pane_index=index,
        )
        for index, (repo_path, branch) in enumerate(pairs)
    ]
    logger.info(
        "runtime-open bootstrap-plan session=%s panes=%s workspace_root=%s",
        session_name,
        split_count,
        workspace_root,
    )
    for index, (repo_path, branch) in enumerate(pairs):
        logger.info(
            "runtime-open bootstrap-pane pane=%s repo=%s branch=%s target=%s",
            index + 1,
            repo_path,
            branch,
            _resolve_wsl_target_path(repo_path, workspace_root=workspace_root, pane_index=index),
        )
    first_startup = startup_commands[0] if startup_commands else "bash"
    lines.append(f"tmux new-session -d -s {session_name} {shlex.quote(first_startup)}")

    for startup in startup_commands[1:]:
        lines.append(f"tmux split-window -t {session_name} {shlex.quote(startup)}")

    extra_panes = max(0, split_count - len(startup_commands))
    for _ in range(extra_panes):
        lines.append(f"tmux split-window -t {session_name}")

    layout_name = "tiled"
    if layout_rows is not None or layout_cols is not None:
        rows, cols = _resolve_runtime_grid_dimensions(
            pane_count=split_count,
            layout_rows=layout_rows,
            layout_cols=layout_cols,
        )
        layout_name = _tmux_layout_name_for_grid(rows, cols)
    lines.append(f"tmux select-layout -t {session_name} {layout_name}")
    lines.extend(_runtime_tmux_style_commands(session_name))
    lines.extend(_runtime_tmux_resize_hook_commands(session_name, layout_name))
    lines.append(f"tmux select-pane -t {session_name}:0.0")
    lines.append(f"tmux attach-session -t {session_name}")
    bootstrap = "; ".join(lines)
    logger.debug("runtime-open bootstrap-command=%s", _truncate_log_text(bootstrap, limit=1400))
    return bootstrap


def build_runtime_wsl_attach_command(
    *,
    pane_paths: list[str],
    layout_rows: int | None = None,
    layout_cols: int | None = None,
    session_name: str = "branchnexus-runtime",
    attach: bool = True,
) -> str:
    resolved_paths = [item.strip() for item in pane_paths if item.strip()]
    if not resolved_paths:
        resolved_paths = ["$HOME"]
    shell_entry = _runtime_interactive_shell_entry()
    startup = f"bash -lc {shlex.quote(shell_entry)}"
    logger.info(
        "runtime-open attach-plan session=%s panes=%s",
        session_name,
        len(resolved_paths),
    )
    lines: list[str] = [
        "tmux start-server",
        f"tmux kill-session -t {session_name} 2>/dev/null || true",
        (
            f"tmux new-session -d -s {session_name} -c {shlex.quote(resolved_paths[0])} "
            f"{shlex.quote(startup)}"
        ),
    ]
    for path in resolved_paths[1:]:
        lines.append(
            f"tmux split-window -t {session_name} -c {shlex.quote(path)} {shlex.quote(startup)}"
        )
    layout_name = "tiled"
    if layout_rows is not None or layout_cols is not None:
        rows, cols = _resolve_runtime_grid_dimensions(
            pane_count=len(resolved_paths),
            layout_rows=layout_rows,
            layout_cols=layout_cols,
        )
        layout_name = _tmux_layout_name_for_grid(rows, cols)
    lines.append(f"tmux select-layout -t {session_name} {layout_name}")
    lines.extend(_runtime_tmux_style_commands(session_name))
    lines.extend(_runtime_tmux_resize_hook_commands(session_name, layout_name))
    lines.append(f"tmux select-pane -t {session_name}:0.0")
    if attach:
        lines.append(f"tmux attach-session -t {session_name}")
    bootstrap = "; ".join(lines)
    logger.debug("runtime-open attach-command=%s", _truncate_log_text(bootstrap, limit=1200))
    return bootstrap


def _build_runtime_wsl_wait_script(*, session_name: str, progress_log_path: str = "") -> str:
    resolved_progress_log = progress_log_path.strip() or _DEFAULT_WSL_PROGRESS_LOG_PATH
    default_progress_log = shlex.quote(_DEFAULT_WSL_PROGRESS_LOG_PATH)
    shell_entry = _runtime_interactive_shell_entry()
    lines: list[str] = [
        'printf "[BranchNexus] Terminal acildi, runtime hazirligi suruyor...\\n"',
        'printf "[BranchNexus] Canli adim loglari bu pencerede goruntulenecek.\\n"',
        (
            "if ! command -v tmux >/dev/null 2>&1; then "
            'printf "[BranchNexus] tmux bulunamadi. Lutfen tmux kurulumunu kontrol edin.\\n"; '
            f"{shell_entry}; fi"
        ),
        'log_tail_pid=""',
    ]
    quoted_path = shlex.quote(resolved_progress_log)
    lines.extend(
        [
            f"progress_log={quoted_path}",
            (f'if [ -z "${{progress_log:-}}" ]; then progress_log={default_progress_log}; fi'),
            'printf "[BranchNexus] Canli log dosyasi: %s\\n" "$progress_log"',
            (
                'if [ -n "${progress_log:-}" ]; then '
                'mkdir -p "$(dirname "$progress_log")" >/dev/null 2>&1 || true; '
                'if touch "$progress_log" >/dev/null 2>&1; then '
                'tail -n +1 -F "$progress_log" & log_tail_pid=$!; '
                "else "
                'printf "[BranchNexus] Canli log dosyasi yazilamadi, tail atlandi.\\n"; '
                "fi; "
                "fi"
            ),
        ]
    )
    lines.extend(
        [
            f"until tmux has-session -t {shlex.quote(session_name)} 2>/dev/null; do sleep 0.25; done",
            (
                'if [ -n "${log_tail_pid:-}" ]; then '
                'kill "$log_tail_pid" >/dev/null 2>&1 || true; '
                'wait "$log_tail_pid" >/dev/null 2>&1 || true; fi'
            ),
            'printf "[BranchNexus] Hazir. Tmux oturumuna baglaniliyor...\\n"',
            f"exec tmux attach-session -t {shlex.quote(session_name)}",
        ]
    )
    return "; ".join(lines)


def build_runtime_wait_open_commands(
    *,
    wsl_distribution: str = "",
    session_name: str = "branchnexus-runtime",
    progress_log_path: str = "",
) -> list[tuple[list[str], int]]:
    wait_script = _build_runtime_wsl_wait_script(
        session_name=session_name,
        progress_log_path=progress_log_path,
    )
    shell_command = ["wsl.exe"]
    if wsl_distribution.strip():
        shell_command.extend(["-d", wsl_distribution.strip()])
    shell_command.extend(["--", "bash", "-lc", wait_script])
    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    commands: list[tuple[list[str], int]] = [(shell_command, creation_flags)]
    logger.debug("runtime-open wait-command-candidates count=%s", len(commands))
    return commands


def open_runtime_waiting_terminal(
    *,
    wsl_distribution: str = "",
    session_name: str = "branchnexus-runtime",
    environ: dict[str, str] | None = None,
    progress_log_path: str = "",
) -> bool:
    launch_env = dict(os.environ)
    if environ:
        launch_env.update(environ)
    command_candidates = build_runtime_wait_open_commands(
        wsl_distribution=wsl_distribution,
        session_name=session_name,
        progress_log_path=progress_log_path,
    )
    logger.info(
        "runtime-open wait-launch-start candidates=%s distribution=%s",
        len(command_candidates),
        wsl_distribution.strip() or "-",
    )
    for index, (command, creation_flags) in enumerate(command_candidates, start=1):
        logger.info(
            "runtime-open wait-launch-candidate index=%s/%s flags=%s command=%s",
            index,
            len(command_candidates),
            creation_flags,
            _command_for_log(command),
        )
        try:
            process = subprocess.Popen(command, creationflags=creation_flags, env=launch_env)
        except OSError:
            logger.debug(
                "Runtime wait terminal candidate failed command=%s", command, exc_info=True
            )
            continue
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            logger.info("runtime-open wait-launch-success index=%s reason=process-running", index)
            return True
        if process.returncode == 0:
            logger.info("runtime-open wait-launch-success index=%s reason=zero-exit", index)
            return True
        logger.warning(
            "runtime-open wait-launch-candidate-failed index=%s code=%s",
            index,
            process.returncode,
        )
    logger.error("Failed to open runtime waiting terminal distribution=%s", wsl_distribution or "-")
    return False


def _run_runtime_wsl_tmux_script(
    *,
    distribution: str,
    script: str,
    step: str,
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> None:
    command = build_wsl_command(distribution, ["bash", "-lc", script])
    logger.debug("runtime-open tmux-run step=%s command=%s", step, _command_for_log(command))
    _emit_terminal_progress(
        verbose_sink,
        level="RUN",
        step=step,
        message=f"command={_command_for_log(command)}",
    )
    run_env = dict(os.environ)
    if env:
        run_env.update(env)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
        **_background_subprocess_kwargs(),
    )
    if result.returncode == 0:
        logger.debug(
            "runtime-open tmux-ok step=%s stdout=%s", step, _truncate_log_text(result.stdout)
        )
        _emit_terminal_progress(
            verbose_sink,
            level="OK",
            step=step,
            message="tmux command completed",
        )
        return
    logger.error(
        "runtime-open tmux-fail step=%s code=%s stderr=%s",
        step,
        result.returncode,
        _truncate_log_text(result.stderr),
    )
    _emit_terminal_progress(
        verbose_sink,
        level="FAIL",
        step=step,
        message=f"code={result.returncode} stderr={_truncate_log_text(result.stderr, limit=220)}",
    )
    raise BranchNexusError(
        f"Runtime tmux adimi basarisiz: {step}",
        code=ExitCode.RUNTIME_ERROR,
        hint=result.stderr.strip() or "WSL tmux komutlarini kontrol edin.",
    )


def reset_runtime_wsl_session(
    *,
    distribution: str,
    session_name: str = "branchnexus-runtime",
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> None:
    _run_runtime_wsl_tmux_script(
        distribution=distribution,
        script=f"tmux kill-session -t {session_name} 2>/dev/null || true",
        step="session-reset",
        env=env,
        verbose_sink=verbose_sink,
    )


def prepare_runtime_wsl_attach_session(
    *,
    distribution: str,
    pane_paths: list[str],
    layout_rows: int | None = None,
    layout_cols: int | None = None,
    session_name: str = "branchnexus-runtime",
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> None:
    script = build_runtime_wsl_attach_command(
        pane_paths=pane_paths,
        layout_rows=layout_rows,
        layout_cols=layout_cols,
        session_name=session_name,
        attach=False,
    )
    _run_runtime_wsl_tmux_script(
        distribution=distribution,
        script=script,
        step="session-prepare",
        env=env,
        verbose_sink=verbose_sink,
    )


def prepare_runtime_wsl_failure_session(
    *,
    distribution: str,
    message: str,
    session_name: str = "branchnexus-runtime",
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> None:
    text = message.strip() or "Open islemi basarisiz oldu."
    shell_entry = (
        f"printf '%s\\n' {shlex.quote('[BranchNexus] Open basarisiz:')} "
        f"{shlex.quote(text)} ; "
        f"{_runtime_interactive_shell_entry()}"
    )
    startup = f"bash -lc {shlex.quote(shell_entry)}"
    script = "; ".join(
        [
            "tmux start-server",
            f"tmux kill-session -t {session_name} 2>/dev/null || true",
            f"tmux new-session -d -s {session_name} {shlex.quote(startup)}",
            *_runtime_tmux_style_commands(session_name),
            f"tmux select-pane -t {session_name}:0.0",
        ]
    )
    _run_runtime_wsl_tmux_script(
        distribution=distribution,
        script=script,
        step="session-failure",
        env=env,
        verbose_sink=verbose_sink,
    )


def build_terminal_launch_commands(
    distribution: str,
    session_name: str = "branchnexus",
    *,
    which: Callable[[str], str | None] = shutil.which,
    environ: dict[str, str] | None = None,
    command_builder: Callable[[str, list[str]], list[str]] = build_wsl_command,
) -> list[tuple[list[str], int]]:
    attach_command = command_builder(distribution, ["tmux", "attach-session", "-t", session_name])

    env = environ or dict(os.environ)
    windows_apps_wt = ""
    local_app_data = env.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        windows_apps_wt = str(Path(local_app_data) / "Microsoft" / "WindowsApps" / "wt.exe")

    wt_candidates = _dedupe(
        [
            value
            for value in [
                which("wt.exe") or "",
                which("wt") or "",
                "wt.exe",
                windows_apps_wt,
            ]
            if value
        ]
    )

    commands: list[tuple[list[str], int]] = []
    for wt_executable in wt_candidates:
        commands.append(([wt_executable, *attach_command], 0))
        commands.append(([wt_executable, "new-tab", "--title", "BranchNexus", *attach_command], 0))

    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    commands.append((attach_command, creation_flags))
    return commands


def launch_tmux_terminal(distribution: str, session_name: str = "branchnexus") -> bool:
    for command, creation_flags in build_terminal_launch_commands(distribution, session_name):
        try:
            process = subprocess.Popen(command, creationflags=creation_flags)
        except OSError:
            logger.debug("Terminal launch candidate failed command=%s", command, exc_info=True)
            continue
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            logger.debug("Launched external terminal command=%s", command)
            return True
        if process.returncode == 0:
            logger.debug("Launched external terminal command=%s", command)
            return True
        logger.debug(
            "Terminal launch candidate exited code=%s command=%s", process.returncode, command
        )
        continue
    logger.error(
        "Failed to launch terminal for tmux attach distribution=%s session=%s",
        distribution,
        session_name,
    )
    return False


def build_runtime_open_commands(
    runtime: RuntimeKind,
    *,
    pane_count: int = 1,
    wsl_distribution: str = "",
    wsl_pane_paths: list[str] | None = None,
    repo_branch_pairs: list[tuple[str, str]] | None = None,
    workspace_root_wsl: str = "",
    layout_rows: int | None = None,
    layout_cols: int | None = None,
    which: Callable[[str], str | None] = shutil.which,
    environ: dict[str, str] | None = None,
) -> list[tuple[list[str], int]]:
    env = environ or dict(os.environ)
    windows_apps_wt = ""
    local_app_data = env.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        windows_apps_wt = str(Path(local_app_data) / "Microsoft" / "WindowsApps" / "wt.exe")

    wt_candidates = _dedupe(
        [
            value
            for value in [
                which("wt.exe") or "",
                which("wt") or "",
                "wt.exe",
                windows_apps_wt,
            ]
            if value
        ]
    )
    if runtime == RuntimeKind.WSL:
        if wsl_pane_paths:
            tmux_bootstrap = build_runtime_wsl_attach_command(
                pane_paths=wsl_pane_paths,
                layout_rows=layout_rows,
                layout_cols=layout_cols,
            )
        else:
            tmux_bootstrap = build_runtime_wsl_bootstrap_command(
                pane_count=pane_count,
                repo_branch_pairs=repo_branch_pairs,
                workspace_root_wsl=workspace_root_wsl,
                layout_rows=layout_rows,
                layout_cols=layout_cols,
            )
        shell_command = ["wsl.exe"]
        if wsl_distribution.strip():
            shell_command.extend(["-d", wsl_distribution.strip()])
        shell_command.extend(["--", "bash", "-lc", tmux_bootstrap])
        # `wt.exe` command parsing splits ';' and breaks tmux bootstrap.
        # For WSL runtime, prefer direct command launch.
        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        commands: list[tuple[list[str], int]] = [(shell_command, creation_flags)]
        logger.debug(
            "runtime-open command-candidates runtime=%s count=%s", runtime.value, len(commands)
        )
        return commands
    else:
        shell_command = ["powershell.exe", "-NoLogo", "-NoProfile"]
    commands: list[tuple[list[str], int]] = []
    for wt_executable in wt_candidates:
        commands.append(([wt_executable, *shell_command], 0))
        commands.append(([wt_executable, "new-tab", "--title", "BranchNexus", *shell_command], 0))

    creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    commands.append((shell_command, creation_flags))
    logger.debug(
        "runtime-open command-candidates runtime=%s count=%s", runtime.value, len(commands)
    )
    return commands


def open_runtime_terminal(
    runtime: RuntimeKind,
    *,
    pane_count: int = 1,
    wsl_distribution: str = "",
    wsl_pane_paths: list[str] | None = None,
    repo_branch_pairs: list[tuple[str, str]] | None = None,
    workspace_root_wsl: str = "",
    layout_rows: int | None = None,
    layout_cols: int | None = None,
    which: Callable[[str], str | None] = shutil.which,
    environ: dict[str, str] | None = None,
) -> bool:
    launch_env = dict(os.environ)
    if environ:
        launch_env.update(environ)
    command_candidates = build_runtime_open_commands(
        runtime,
        pane_count=pane_count,
        wsl_distribution=wsl_distribution,
        wsl_pane_paths=wsl_pane_paths,
        repo_branch_pairs=repo_branch_pairs,
        workspace_root_wsl=workspace_root_wsl,
        layout_rows=layout_rows,
        layout_cols=layout_cols,
        which=which,
        environ=environ,
    )
    logger.info(
        "runtime-open launch-start runtime=%s candidates=%s pane_count=%s distribution=%s",
        runtime.value,
        len(command_candidates),
        pane_count,
        wsl_distribution.strip() or "-",
    )
    for index, (command, creation_flags) in enumerate(command_candidates, start=1):
        logger.info(
            "runtime-open launch-candidate index=%s/%s flags=%s command=%s",
            index,
            len(command_candidates),
            creation_flags,
            _command_for_log(command),
        )
        try:
            process = subprocess.Popen(command, creationflags=creation_flags, env=launch_env)
        except OSError:
            logger.debug(
                "Runtime terminal launch candidate failed command=%s", command, exc_info=True
            )
            continue

        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            logger.debug("Runtime terminal launched command=%s", command)
            logger.info("runtime-open launch-success index=%s reason=process-running", index)
            return True

        if process.returncode == 0:
            logger.debug("Runtime terminal launched command=%s", command)
            logger.info("runtime-open launch-success index=%s reason=zero-exit", index)
            return True
        logger.debug(
            "Runtime terminal launch exited code=%s command=%s", process.returncode, command
        )
        logger.warning(
            "runtime-open launch-candidate-failed index=%s code=%s",
            index,
            process.returncode,
        )
    logger.error("Failed to open runtime terminal runtime=%s", runtime.value)
    return False


def launch_runtime_dashboard(
    *,
    config: AppConfig,
    state: AppState,
    config_path: str | Path | None = None,
    run_ui: bool = False,
) -> int:
    default_runtime = RuntimeKind.WSL
    if config.terminal_default_runtime != RuntimeKind.WSL.value:
        logger.info(
            "runtime-v2 forcing-default-runtime runtime=%s forced=%s",
            config.terminal_default_runtime,
            RuntimeKind.WSL.value,
        )
        config.terminal_default_runtime = RuntimeKind.WSL.value
        save_config(config, config_path)

    service = TerminalService(
        max_terminals=config.terminal_max_count,
        default_runtime=default_runtime,
    )
    dashboard = RuntimeDashboardScreen(
        service,
        template=config.default_panes,
        custom_terminal_count=config.default_panes,
        default_runtime=default_runtime,
    )

    restored = False
    if config.session_restore_enabled:
        snapshot = parse_runtime_snapshot(config.last_session)
        if snapshot is not None:
            snapshot_payload = snapshot.to_dict()
            terminals_payload = snapshot_payload.get("terminals", [])
            if isinstance(terminals_payload, list):
                for item in terminals_payload:
                    if isinstance(item, dict):
                        item["runtime"] = RuntimeKind.WSL.value
            restored = dashboard.restore_snapshot(snapshot_payload)

    if not restored:
        dashboard.bootstrap()

    panels = dashboard.list_panels()
    state.terminal_template = dashboard.template_count
    state.max_terminals = config.terminal_max_count
    state.terminal_default_runtime = default_runtime.value
    state.focused_terminal_id = dashboard.focused_terminal_id or (
        panels[0].terminal_id if panels else ""
    )

    def persist_snapshot() -> None:
        if not config.session_restore_enabled:
            return
        snapshot = build_runtime_snapshot(
            layout=config.default_layout,
            template_count=dashboard.template_count,
            terminals=service.list_instances(),
            focused_terminal_id=dashboard.focused_terminal_id,
        )
        config.last_session = snapshot.to_dict()
        save_config(config, config_path)

    persist_snapshot()
    if not run_ui:
        return int(ExitCode.SUCCESS)

    try:
        from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
            QGridLayout,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSpinBox,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        raise BranchNexusError(
            "PySide6 kurulu degil; runtime dashboard acilamadi.",
            code=ExitCode.RUNTIME_ERROR,
            hint="`pip install PySide6` komutunu calistirip tekrar deneyin.",
        ) from exc

    class RepoLoadWorker(QObject):  # pragma: no cover
        succeeded = Signal(object, object)  # repositories, branches_by_repo
        failed = Signal(str)
        finished = Signal()

        def __init__(self, token: str) -> None:
            super().__init__()
            self.token = token

        @Slot()
        def run(self) -> None:
            try:
                repositories = list_github_repositories(self.token)
                branches_by_repo: dict[str, list[str]] = {}
                for repository in repositories:
                    try:
                        branches_by_repo[repository.full_name] = list_github_repository_branches(
                            self.token,
                            repository.full_name,
                        )
                    except BranchNexusError:
                        branches_by_repo[repository.full_name] = []
                self.succeeded.emit(repositories, branches_by_repo)
            except BranchNexusError as exc:
                self.failed.emit(str(exc))
            except Exception as exc:
                self.failed.emit(str(exc))
            finally:
                self.finished.emit()

    class BranchLoadWorker(QObject):  # pragma: no cover
        succeeded = Signal(str, str, object)  # repo_name, terminal_id, branches
        failed = Signal(str, str, str)  # repo_name, terminal_id, message
        finished = Signal()

        def __init__(self, token: str, repo_name: str, terminal_id: str) -> None:
            super().__init__()
            self.token = token
            self.repo_name = repo_name
            self.terminal_id = terminal_id

        @Slot()
        def run(self) -> None:
            try:
                branches = list_github_repository_branches(self.token, self.repo_name)
                self.succeeded.emit(self.repo_name, self.terminal_id, branches)
            except BranchNexusError as exc:
                self.failed.emit(self.repo_name, self.terminal_id, str(exc))
            except Exception as exc:
                self.failed.emit(self.repo_name, self.terminal_id, str(exc))
            finally:
                self.finished.emit()

    class OpenTerminalWorker(QObject):  # pragma: no cover
        succeeded = Signal(object)  # {"pane_count": int}
        progress = Signal(str, str)  # step, message
        failed = Signal(str, str)  # kind, message
        finished = Signal()

        def __init__(
            self,
            *,
            runtime: RuntimeKind,
            pane_count: int,
            layout_rows: int,
            layout_cols: int,
            wsl_distribution: str,
            wsl_pairs: list[tuple[str, str]],
            workspace_root_wsl: str,
            github_token: str,
            terminal_font_size: int,
        ) -> None:
            super().__init__()
            self.runtime = runtime
            self.pane_count = pane_count
            self.layout_rows = layout_rows
            self.layout_cols = layout_cols
            self.wsl_distribution = wsl_distribution
            self.wsl_pairs = wsl_pairs
            self.workspace_root_wsl = workspace_root_wsl
            self.github_token = github_token.strip()
            self.terminal_font_size = max(8, min(24, int(terminal_font_size)))

        @Slot()
        def run(self) -> None:
            pane_count = self.pane_count
            prepared_wsl_paths: list[str] = []
            launch_env = None
            if self.github_token:
                launch_env = {
                    "BRANCHNEXUS_GH_TOKEN": self.github_token,
                    "GH_TOKEN": self.github_token,
                    "GITHUB_TOKEN": self.github_token,
                }
            progress_log_path = ""
            terminal_progress_sink: Callable[[str], None] | None = None
            try:
                if self.runtime == RuntimeKind.WSL:
                    if not self.wsl_distribution.strip():
                        raise BranchNexusError(
                            "WSL dagitimi secilmedi.",
                            code=ExitCode.VALIDATION_ERROR,
                        )
                    workspace_root = _resolve_runtime_workspace_root_wsl(
                        self.wsl_distribution,
                        self.workspace_root_wsl,
                    )
                    progress_log_path = _build_runtime_progress_log_path(workspace_root)
                    if not progress_log_path:
                        progress_log_path = _DEFAULT_WSL_PROGRESS_LOG_PATH
                        logger.warning(
                            "runtime-open progress-log-path-empty using-default=%s",
                            progress_log_path,
                        )
                    _init_wsl_progress_log(
                        distribution=self.wsl_distribution,
                        log_path=progress_log_path,
                        env=launch_env,
                    )

                    def terminal_progress_sink(
                        line: str,
                        *,
                        _distribution: str = self.wsl_distribution,
                        _path: str = progress_log_path,
                        _env: dict[str, str] | None = launch_env,
                    ) -> None:
                        logger.info("runtime-open live %s", line)
                        _append_wsl_progress_log(
                            distribution=_distribution,
                            log_path=_path,
                            line=line,
                            env=_env,
                        )

                    terminal_progress_sink(
                        _format_terminal_progress_line(
                            "INFO",
                            "open-start",
                            (
                                f"workspace={workspace_root} runtime=wsl "
                                f"pane_count={self.pane_count}"
                            ),
                        )
                    )
                    self.progress.emit("open-preflight", "Runtime hazirlik adimlari baslatildi...")
                    self.progress.emit("tmux-bootstrap", "tmux kontrol ediliyor...")
                    ensure_tmux(
                        self.wsl_distribution,
                        auto_install=True,
                        runner=subprocess.run,
                    )
                    self.progress.emit("tmux-bootstrap", "tmux hazir.")
                    reset_runtime_wsl_session(
                        distribution=self.wsl_distribution,
                        env=launch_env,
                        verbose_sink=terminal_progress_sink,
                    )

                    def preflight_progress(step: str, message: str) -> None:
                        self.progress.emit(step, message)

                    prepared_wsl_paths = prepare_wsl_runtime_pane_paths(
                        distribution=self.wsl_distribution,
                        repo_branch_pairs=self.wsl_pairs,
                        workspace_root_wsl=workspace_root,
                        github_token=self.github_token,
                        progress=preflight_progress,
                        verbose_sink=terminal_progress_sink,
                    )
                    pane_count = max(1, len(prepared_wsl_paths))
                    font_applied, font_reason = _apply_windows_terminal_profile_font_size(
                        distribution=self.wsl_distribution,
                        font_size=self.terminal_font_size,
                    )
                    if font_applied:
                        self.progress.emit(
                            "terminal-font",
                            f"Terminal yazi boyutu uygulandi: {self.terminal_font_size}px",
                        )
                    else:
                        logger.info(
                            "runtime-open terminal-font-skip distribution=%s reason=%s",
                            self.wsl_distribution,
                            font_reason,
                        )
                    self.progress.emit("open-session", "WSL terminali aciliyor...")
                    opened = open_runtime_terminal(
                        RuntimeKind.WSL,
                        pane_count=pane_count,
                        wsl_distribution=self.wsl_distribution,
                        wsl_pane_paths=prepared_wsl_paths,
                        layout_rows=self.layout_rows,
                        layout_cols=self.layout_cols,
                        environ=launch_env,
                    )
                else:
                    opened = open_runtime_terminal(
                        self.runtime,
                        pane_count=pane_count,
                        wsl_distribution=self.wsl_distribution,
                        wsl_pane_paths=prepared_wsl_paths or None,
                        repo_branch_pairs=self.wsl_pairs,
                        workspace_root_wsl=self.workspace_root_wsl,
                        layout_rows=self.layout_rows,
                        layout_cols=self.layout_cols,
                        environ=launch_env,
                    )
            except BranchNexusError as exc:
                self.failed.emit("open-preflight-failed", str(exc))
                self.finished.emit()
                return
            except Exception as exc:
                logger.exception("runtime-open worker-unexpected-failure")
                self.failed.emit("open-preflight-failed", str(exc))
                self.finished.emit()
                return

            if not opened:
                self.failed.emit("open-failed", "Terminal acilamadi.")
                self.finished.emit()
                return

            self.succeeded.emit({"pane_count": pane_count})
            self.finished.emit()

    class RuntimeDashboardWindow(QMainWindow):  # pragma: no cover
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("BranchNexus Calisma Paneli")
            self.resize(950, 640)

            root = QWidget(self)
            self.setCentralWidget(root)
            layout = QVBoxLayout(root)
            self._repositories_by_name: dict[str, GitHubRepository] = {}
            self._branches_by_repo: dict[str, list[str]] = {}
            self._repo_combo_by_terminal: dict[str, QComboBox] = {}
            self._branch_combo_by_terminal: dict[str, QComboBox] = {}
            self._pending_repo_by_terminal: dict[str, str] = {}
            self._pending_branch_by_terminal: dict[str, str] = {}
            self._updating_table = False
            self._repo_load_thread: QThread | None = None
            self._repo_load_worker: RepoLoadWorker | None = None
            self._branch_load_thread: QThread | None = None
            self._branch_load_worker: BranchLoadWorker | None = None
            self._branch_load_terminal_id = ""
            self._branch_load_repo_name = ""
            self._open_thread: QThread | None = None
            self._open_worker: OpenTerminalWorker | None = None
            self._open_request_terminal_id = ""
            self._open_request_runtime = RuntimeKind.WSL.value
            self._open_request_pane_count = 1
            self._spinner_frames = ("|", "/", "-", "\\")
            self._load_spinner_index = 0
            self._open_spinner_index = 0
            self._available_wsl_distributions: list[str] = []
            self._hydrate_repository_cache_from_config()
            self._template_cards: dict[int, QPushButton] = {}
            self._template_dimensions: dict[int, tuple[int, int]] = {}
            self._terminal_font_size = 10

            controls = QGridLayout()
            controls.setContentsMargins(0, 0, 0, 0)
            controls.setHorizontalSpacing(4)
            controls.setVerticalSpacing(6)
            controls.setColumnMinimumWidth(0, 45)
            controls.setColumnStretch(1, 1)

            self.grid_rows_spin = QSpinBox()
            self.grid_rows_spin.setRange(1, 16)
            self.grid_rows_spin.setValue(2)
            self.grid_rows_spin.setFixedWidth(65)
            self.grid_rows_spin.setFixedHeight(28)
            self.grid_rows_spin.setProperty("grid_compact", True)
            self.grid_rows_spin.setToolTip("Satir sayisi")

            self.grid_cols_spin = QSpinBox()
            self.grid_cols_spin.setRange(1, 16)
            self.grid_cols_spin.setValue(2)
            self.grid_cols_spin.setFixedWidth(65)
            self.grid_cols_spin.setFixedHeight(28)
            self.grid_cols_spin.setProperty("grid_compact", True)
            self.grid_cols_spin.setToolTip("Sutun sayisi")

            self.font_size_spin = QSpinBox()
            self.font_size_spin.setRange(8, 24)
            self.font_size_spin.setValue(self._terminal_font_size)
            self.font_size_spin.setFixedWidth(65)
            self.font_size_spin.setFixedHeight(28)
            self.font_size_spin.setProperty("grid_compact", True)
            self.font_size_spin.setToolTip("Acilan split terminal yazisi (px)")

            self.grid_apply_btn = QPushButton("Uygula")
            self.grid_apply_btn.setProperty("secondary_btn", True)
            self.grid_apply_btn.setFixedWidth(80)
            self.grid_apply_btn.setFixedHeight(34)
            grid_controls = QWidget()
            grid_controls_row = QHBoxLayout(grid_controls)
            grid_controls_row.setContentsMargins(0, 0, 0, 0)
            grid_controls_row.setSpacing(4)
            grid_title_label = QLabel("↔")
            grid_title_label.setProperty("grid_title_label", True)
            grid_controls_row.addWidget(grid_title_label)
            grid_controls_row.addSpacing(2)
            grid_controls_row.addWidget(self.grid_rows_spin)
            grid_mul_label = QLabel("x")
            grid_mul_label.setProperty("grid_separator", True)
            grid_controls_row.addWidget(grid_mul_label)
            grid_controls_row.addWidget(self.grid_cols_spin)
            grid_controls_row.addSpacing(4)
            font_title_label = QLabel("F")
            font_title_label.setProperty("grid_title_label", True)
            grid_controls_row.addWidget(font_title_label)
            grid_controls_row.addWidget(self.font_size_spin)
            grid_controls_row.addStretch(1)

            self.add_btn = QPushButton("Ekle")
            self.add_btn.setProperty("secondary_btn", True)
            self.remove_btn = QPushButton("Kaldir")
            self.remove_btn.setProperty("secondary_btn", True)
            self.open_btn = QPushButton("Baslat")
            self.open_btn.setProperty("action_btn", True)
            self.add_btn.setFixedWidth(80)
            self.remove_btn.setFixedWidth(80)
            self.open_btn.setFixedWidth(90)
            self.add_btn.setFixedHeight(34)
            self.remove_btn.setFixedHeight(34)
            self.open_btn.setFixedHeight(34)
            self.open_spinner = QLabel("")
            self.open_spinner.setMinimumWidth(24)
            self.open_spinner.setMinimumHeight(36)
            self.open_spinner.setStyleSheet("color: #5ec2f2;")
            terminal_actions = QWidget()
            terminal_actions_row = QHBoxLayout(terminal_actions)
            terminal_actions_row.setContentsMargins(0, 0, 0, 0)
            terminal_actions_row.setSpacing(6)
            terminal_actions_row.addWidget(self.add_btn)
            terminal_actions_row.addWidget(self.remove_btn)
            terminal_actions_row.addWidget(self.open_btn)
            terminal_actions_row.addWidget(self.open_spinner)
            terminal_actions_row.addStretch(0)
            terminal_actions_row.addWidget(grid_controls, 0, Qt.AlignmentFlag.AlignLeft)
            controls.addWidget(QLabel("Term"), 2, 0)
            controls.addWidget(terminal_actions, 2, 1)
            controls.addWidget(self.grid_apply_btn, 2, 2, Qt.AlignmentFlag.AlignLeft)
            self.open_spinner_timer = QTimer(self)
            self.open_spinner_timer.setInterval(90)
            self.open_spinner_timer.timeout.connect(self._tick_open_spinner)

            controls.addWidget(QLabel("Token"), 0, 0)
            self.github_token_edit = QLineEdit(config.github_token)
            self.github_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.github_token_edit.setPlaceholderText("ghp_xxx")
            self.github_token_edit.setFixedHeight(34)
            controls.addWidget(self.github_token_edit, 0, 1)
            self.load_repos_btn = QPushButton("Getir")
            self.load_repos_btn.setProperty("secondary_btn", True)
            self.load_repos_btn.setFixedWidth(75)
            self.load_repos_btn.setFixedHeight(34)
            self.load_spinner = QLabel("")
            self.load_spinner.setMinimumWidth(24)
            self.load_spinner.setStyleSheet("color: #5ec2f2;")
            repo_actions = QWidget()
            repo_actions_row = QHBoxLayout(repo_actions)
            repo_actions_row.setContentsMargins(0, 0, 0, 0)
            repo_actions_row.setSpacing(6)
            repo_actions_row.addWidget(self.load_repos_btn)
            repo_actions_row.addWidget(self.load_spinner)
            repo_actions_row.addStretch(1)
            controls.addWidget(repo_actions, 0, 2, Qt.AlignmentFlag.AlignLeft)
            self.load_spinner_timer = QTimer(self)
            self.load_spinner_timer.setInterval(90)
            self.load_spinner_timer.timeout.connect(self._tick_spinner)

            controls.addWidget(QLabel("WSL"), 1, 0)
            self.wsl_distribution_combo = QComboBox()
            self.wsl_distribution_combo.setMinimumContentsLength(20)
            self.wsl_distribution_combo.setFixedHeight(34)
            controls.addWidget(self.wsl_distribution_combo, 1, 1)
            self.reload_wsl_btn = QPushButton("Yenile")
            self.reload_wsl_btn.setProperty("secondary_btn", True)
            self.reload_wsl_btn.setFixedWidth(75)
            self.reload_wsl_btn.setFixedHeight(34)
            controls.addWidget(self.reload_wsl_btn, 1, 2, Qt.AlignmentFlag.AlignLeft)

            layout.addLayout(controls)

            cards_layout = QGridLayout()
            cards_layout.setContentsMargins(0, 4, 0, 10)
            cards_layout.setHorizontalSpacing(10)
            cards_layout.setVerticalSpacing(0)
            template_specs = [
                (2, 1, 2),
                (3, 1, 3),
                (4, 2, 2),
                (6, 2, 3),
                (8, 2, 4),
                (9, 3, 3),
                (12, 3, 4),
                (16, 4, 4),
            ]
            for index, (count, preview_rows, preview_cols) in enumerate(template_specs):
                preview = self._template_preview(preview_rows, preview_cols)
                card = QPushButton(f"{count}\n{preview}")
                card.setCheckable(True)
                card.setProperty("template_card", True)
                card.setCursor(Qt.CursorShape.PointingHandCursor)
                card.setFixedSize(94, 94)
                card.setToolTip(f"{count} terminal")
                row = 0
                col = index
                cards_layout.addWidget(card, row, col)
                card.clicked.connect(
                    lambda _checked, value=count: self._set_template_from_card(value)
                )
                self._template_cards[count] = card
                self._template_dimensions[count] = (preview_rows, preview_cols)
            cards_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            layout.addLayout(cards_layout)

            self.table = QTableWidget(0, 4)
            self.table.setHorizontalHeaderLabels(["Terminal", "Baslik", "Depo", "Dal"])
            self._terminal_row_height = 36
            self._terminal_cell_height = 34
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            self.table.verticalHeader().setDefaultSectionSize(self._terminal_row_height)
            self.table.verticalHeader().setMinimumSectionSize(self._terminal_row_height)
            self.table.verticalHeader().setMaximumSectionSize(self._terminal_row_height)
            self.table.horizontalHeader().setStretchLastSection(False)
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self._apply_table_column_widths()
            layout.addWidget(self.table)

            self.status = QLabel("")
            layout.addWidget(self.status)

            self.add_btn.clicked.connect(self._add_terminal)
            self.remove_btn.clicked.connect(self._remove_terminal)
            self.open_btn.clicked.connect(self._open_terminal)
            self.grid_apply_btn.clicked.connect(self._apply_grid_template)
            self.load_repos_btn.clicked.connect(self._load_repositories)
            self.reload_wsl_btn.clicked.connect(self._load_wsl_distributions)
            self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
            self.wsl_distribution_combo.currentTextChanged.connect(
                self._on_wsl_distribution_changed
            )
            self.table.itemSelectionChanged.connect(self._focus_selected)
            self._apply_visual_style()

            self._load_wsl_distributions(initial=True)
            self._sync_grid_inputs_from_count(dashboard.template_count)
            self._select_template_card(dashboard.template_count)
            self._refresh()
            if self._repositories_by_name:
                self._set_status(
                    f"{len(self._repositories_by_name)} kayitli repo otomatik yuklendi."
                )
            elif self.github_token_edit.text().strip():
                QTimer.singleShot(0, self._load_repositories)

        def _set_status(self, message: str, *, error: bool = False) -> None:
            self.status.setText(message)
            self.status.setStyleSheet("color: #b00020;" if error else "")

        def _hydrate_repository_cache_from_config(self) -> None:
            repositories: dict[str, GitHubRepository] = {}
            for item in config.github_repositories_cache:
                if not isinstance(item, dict):
                    continue
                full_name_raw = item.get("full_name")
                clone_url_raw = item.get("clone_url")
                if not isinstance(full_name_raw, str) or not isinstance(clone_url_raw, str):
                    continue
                full_name = full_name_raw.strip()
                clone_url = clone_url_raw.strip()
                if not full_name or not clone_url:
                    continue
                repositories[full_name] = GitHubRepository(full_name=full_name, clone_url=clone_url)
            self._repositories_by_name = repositories

            branches_by_repo: dict[str, list[str]] = {}
            for repo_name, branches in config.github_branches_cache.items():
                if not isinstance(repo_name, str) or not isinstance(branches, list):
                    continue
                key = repo_name.strip()
                if not key:
                    continue
                normalized_branches = [
                    branch.strip()
                    for branch in branches
                    if isinstance(branch, str) and branch.strip()
                ]
                branches_by_repo[key] = normalized_branches
            self._branches_by_repo = branches_by_repo

        def _persist_repository_cache(self) -> None:
            config.github_token = self.github_token_edit.text().strip()
            config.github_repositories_cache = [
                {"full_name": repository.full_name, "clone_url": repository.clone_url}
                for repository in sorted(
                    self._repositories_by_name.values(), key=lambda item: item.full_name.lower()
                )
            ]
            config.github_branches_cache = {
                repo_name: [
                    branch for branch in branches if isinstance(branch, str) and branch.strip()
                ]
                for repo_name, branches in sorted(self._branches_by_repo.items())
                if isinstance(repo_name, str) and repo_name.strip()
            }
            save_config(config, config_path)

        def _load_wsl_distributions(self, *, initial: bool = False) -> None:
            previous = self.wsl_distribution_combo.currentText().strip()
            configured = config.wsl_distribution.strip()
            try:
                distributions = list_distributions()
            except BranchNexusError as exc:
                self._available_wsl_distributions = []
                self.wsl_distribution_combo.blockSignals(True)
                self.wsl_distribution_combo.clear()
                self.wsl_distribution_combo.blockSignals(False)
                if not initial:
                    self._set_status(str(exc), error=True)
                logger.warning("runtime-open wsl-discovery-failed error=%s", exc.message)
                return

            self._available_wsl_distributions = distributions
            selected = select_runtime_wsl_distribution(
                distributions,
                configured=configured,
                current=previous,
            )

            self.wsl_distribution_combo.blockSignals(True)
            self.wsl_distribution_combo.clear()
            self.wsl_distribution_combo.addItems(distributions)
            if selected:
                self.wsl_distribution_combo.setCurrentText(selected)
            self.wsl_distribution_combo.blockSignals(False)

            if selected and config.wsl_distribution != selected:
                config.wsl_distribution = selected
                save_config(config, config_path)
            logger.info(
                "runtime-open wsl-discovery-success count=%s selected=%s",
                len(distributions),
                selected or "-",
            )

        def _on_wsl_distribution_changed(self, value: str) -> None:
            selected = value.strip()
            if not selected:
                return
            if selected == config.wsl_distribution:
                return
            config.wsl_distribution = selected
            save_config(config, config_path)
            logger.info("runtime-open wsl-selected distribution=%s", selected)
            self._set_status(f"WSL secildi: {selected}")

        def _selected_wsl_distribution(self) -> str:
            selected = self.wsl_distribution_combo.currentText().strip()
            if selected:
                return selected
            return config.wsl_distribution.strip()

        def _apply_table_column_widths(self) -> None:
            self.table.setColumnWidth(0, 100)  # Terminal
            self.table.setColumnWidth(1, 210)  # Baslik
            self.table.setColumnWidth(2, 460)  # Depo
            self.table.setColumnWidth(3, 240)  # Dal

        def _on_font_size_changed(self, value: int) -> None:
            self._terminal_font_size = max(8, min(24, int(value)))
            self._set_status(
                f"Terminal yazi boyutu ayarlandi: {self._terminal_font_size}px "
                "(bir sonraki Ac isleminde uygulanir)"
            )

        def _tick_spinner(self) -> None:
            frame = self._spinner_frames[self._load_spinner_index % len(self._spinner_frames)]
            self._load_spinner_index += 1
            self.load_spinner.setText(frame)

        def _tick_open_spinner(self) -> None:
            frame = self._spinner_frames[self._open_spinner_index % len(self._spinner_frames)]
            self._open_spinner_index += 1
            self.open_spinner.setText(frame)

        def _start_repo_loading_indicator(self) -> None:
            self._load_spinner_index = 0
            self.load_spinner.setText(self._spinner_frames[0])
            self.load_spinner_timer.start()
            self.load_repos_btn.setEnabled(False)

        def _stop_repo_loading_indicator(self) -> None:
            self.load_spinner_timer.stop()
            self.load_spinner.setText("")
            self.load_repos_btn.setEnabled(True)

        def _start_open_loading_indicator(self) -> None:
            self._open_spinner_index = 0
            self.open_spinner.setText(self._spinner_frames[0])
            self.open_spinner_timer.start()
            self.open_btn.setEnabled(False)
            self.add_btn.setEnabled(False)
            self.remove_btn.setEnabled(False)
            self.grid_apply_btn.setEnabled(False)
            self.grid_rows_spin.setEnabled(False)
            self.grid_cols_spin.setEnabled(False)
            self.font_size_spin.setEnabled(False)
            for card in self._template_cards.values():
                card.setEnabled(False)
            self.table.setEnabled(False)

        def _stop_open_loading_indicator(self) -> None:
            self.open_spinner_timer.stop()
            self.open_spinner.setText("")
            self.open_btn.setEnabled(True)
            self.add_btn.setEnabled(True)
            self.remove_btn.setEnabled(True)
            self.grid_apply_btn.setEnabled(True)
            self.grid_rows_spin.setEnabled(True)
            self.grid_cols_spin.setEnabled(True)
            self.font_size_spin.setEnabled(True)
            for card in self._template_cards.values():
                card.setEnabled(True)
            self.table.setEnabled(True)

        def _selected_terminal_id(self) -> str:
            indexes = self.table.selectionModel().selectedRows()
            if not indexes:
                return ""
            row = indexes[0].row()
            item = self.table.item(row, 0)
            if item is None:
                return ""
            return item.text().strip()

        def _focus_selected(self) -> None:
            if self._updating_table:
                return
            terminal_id = self._selected_terminal_id()
            if not terminal_id:
                return
            try:
                dashboard.focus_terminal(terminal_id)
            except BranchNexusError:
                return
            self._refresh()

        def _set_template_from_card(self, count: int) -> None:
            try:
                dashboard.set_template(str(count))
            except BranchNexusError as exc:
                self._set_status(str(exc), error=True)
                return
            self._sync_grid_inputs_from_count(count)
            self._select_template_card(dashboard.template_count)
            self._set_status(f"Sablon uygulandi: {dashboard.template_count} terminal")
            self._refresh()

        def _apply_grid_template(self) -> None:
            rows = self.grid_rows_spin.value()
            cols = self.grid_cols_spin.value()
            requested = rows * cols
            try:
                dashboard.set_template(str(requested))
            except BranchNexusError:
                self._set_status(
                    "Satir x sutun sonucu 2 ile 16 arasinda olmali.",
                    error=True,
                )
                return
            self._select_template_card(dashboard.template_count)
            self._set_status(f"{rows}x{cols} ile {dashboard.template_count} terminal olusturuldu.")
            self._refresh()

        def _sync_grid_inputs_from_count(self, count: int) -> None:
            dimensions = self._template_dimensions.get(count)
            if dimensions is None:
                dimensions = (1, count)
            rows, cols = dimensions
            self.grid_rows_spin.blockSignals(True)
            self.grid_cols_spin.blockSignals(True)
            self.grid_rows_spin.setValue(rows)
            self.grid_cols_spin.setValue(cols)
            self.grid_rows_spin.blockSignals(False)
            self.grid_cols_spin.blockSignals(False)

        def _add_terminal(self) -> None:
            try:
                dashboard.add_terminal(runtime=RuntimeKind.WSL)
            except BranchNexusError as exc:
                self._set_status(str(exc), error=True)
                return
            self._set_status("Terminal eklendi.")
            self._refresh()

        def _load_repositories(self) -> None:
            if self._repo_load_thread is not None:
                self._set_status("Repo listesi yukleniyor, lutfen bekleyin.")
                return
            token = self.github_token_edit.text().strip()
            if not token:
                self._set_status("GitHub token girilmedi.", error=True)
                return
            self._start_repo_loading_indicator()
            self._set_status("Repo listesi yukleniyor...")

            thread = QThread(self)
            worker = RepoLoadWorker(token)
            worker.moveToThread(thread)

            thread.started.connect(worker.run)
            worker.succeeded.connect(self._on_repo_load_success)
            worker.failed.connect(self._on_repo_load_failed)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._on_repo_load_done)

            self._repo_load_thread = thread
            self._repo_load_worker = worker
            thread.start()

        def _on_repo_load_success(self, repositories: object, branches_by_repo: object) -> None:
            if not isinstance(repositories, list):
                self._set_status("Repo listesi beklenmeyen formatta.", error=True)
                return
            if not isinstance(branches_by_repo, dict):
                self._set_status("Branch listesi beklenmeyen formatta.", error=True)
                return
            self._repositories_by_name = {
                item.full_name: item for item in repositories if isinstance(item, GitHubRepository)
            }
            self._branches_by_repo = {
                str(name): [
                    branch for branch in values if isinstance(branch, str) and branch.strip()
                ]
                if isinstance(values, list)
                else []
                for name, values in branches_by_repo.items()
            }
            self._persist_repository_cache()
            self._refresh()
            self._set_status(f"{len(self._repositories_by_name)} repo yuklendi.")

        def _on_repo_load_failed(self, message: str) -> None:
            self._set_status(message or "Repo listesi yuklenemedi.", error=True)

        def _on_repo_load_done(self) -> None:
            self._stop_repo_loading_indicator()
            self._repo_load_worker = None
            self._repo_load_thread = None

        def _load_branches_for_repo(self, repo_full_name: str) -> list[str]:
            repo_name = repo_full_name.strip()
            if not repo_name:
                return []
            return self._branches_by_repo.get(repo_name, [])

        def _load_branches_async(self, *, terminal_id: str, repo_name: str) -> None:
            if self._branch_load_thread is not None:
                self._set_status("Branch listesi yukleniyor, lutfen bekleyin.")
                return

            token = self.github_token_edit.text().strip()
            if not token:
                self._set_status("Branch yuklemek icin GitHub token girin.", error=True)
                return

            thread = QThread(self)
            worker = BranchLoadWorker(token, repo_name, terminal_id)
            worker.moveToThread(thread)

            thread.started.connect(worker.run)
            worker.succeeded.connect(self._on_branch_load_success)
            worker.failed.connect(self._on_branch_load_failed)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._on_branch_load_done)

            self._branch_load_thread = thread
            self._branch_load_worker = worker
            self._branch_load_terminal_id = terminal_id
            self._branch_load_repo_name = repo_name
            self._set_status(f"{repo_name} icin branch listesi yukleniyor...")
            thread.start()

        def _on_branch_load_success(
            self, repo_name: str, terminal_id: str, branches_payload: object
        ) -> None:
            if not isinstance(branches_payload, list):
                self._set_status(f"{repo_name} branch listesi beklenmeyen formatta.", error=True)
                return

            branches = [item for item in branches_payload if isinstance(item, str) and item.strip()]
            self._branches_by_repo[repo_name] = branches
            self._persist_repository_cache()
            if terminal_id:
                self._pending_branch_by_terminal[terminal_id] = branches[0] if branches else ""
            self._refresh()
            if terminal_id and branches:
                self._apply_auto_switch(terminal_id)
            self._set_status(f"{repo_name} icin {len(branches)} branch yuklendi.")

        def _on_branch_load_failed(self, repo_name: str, _terminal_id: str, message: str) -> None:
            self._set_status(message or f"{repo_name} branch listesi yuklenemedi.", error=True)

        def _on_branch_load_done(self) -> None:
            self._branch_load_worker = None
            self._branch_load_thread = None
            self._branch_load_terminal_id = ""
            self._branch_load_repo_name = ""

        def _remove_terminal(self) -> None:
            terminal_id = self._selected_terminal_id()
            if not terminal_id:
                self._set_status("Silinecek terminal secilmedi.", error=True)
                return

            dialog = QMessageBox(self)
            dialog.setWindowTitle("Remove Terminal")
            dialog.setText(f"{terminal_id} silinsin mi?")
            preserve_btn = dialog.addButton("Koruyarak Sil", QMessageBox.ButtonRole.ActionRole)
            clean_btn = dialog.addButton("Temizleyerek Sil", QMessageBox.ButtonRole.DestructiveRole)
            dialog.addButton("Vazgec", QMessageBox.ButtonRole.RejectRole)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked not in {preserve_btn, clean_btn}:
                return

            cleanup = "clean" if clicked is clean_btn else "preserve"
            self._remove_terminal_by_id(terminal_id, cleanup=cleanup, announce=True)

        def _remove_terminal_by_id(
            self, terminal_id: str, *, cleanup: str = "preserve", announce: bool = True
        ) -> None:
            try:
                dashboard.remove_terminal(terminal_id, cleanup=cleanup)
            except BranchNexusError as exc:
                self._set_status(str(exc), error=True)
                return
            self._pending_repo_by_terminal.pop(terminal_id, None)
            self._pending_branch_by_terminal.pop(terminal_id, None)
            if announce:
                self._set_status(f"{terminal_id} kaldirildi ({cleanup}).")
            self._refresh()

        def _remove_terminal_inline(self, terminal_id: str) -> None:
            self._remove_terminal_by_id(terminal_id, cleanup="preserve", announce=True)

        def _open_terminal(self) -> None:
            if self._open_thread is not None:
                self._set_status("Open islemi devam ediyor, lutfen bekleyin.")
                return

            terminal_id = self._selected_terminal_id()
            if not terminal_id:
                self._set_status("Acilacak terminal secilmedi.", error=True)
                return

            instance = None
            for item in service.list_instances():
                if item.spec.terminal_id == terminal_id:
                    instance = item
                    break
            if instance is None:
                self._set_status("Terminal bulunamadi.", error=True)
                return

            if instance.spec.runtime != RuntimeKind.WSL:
                self._set_status("Bu surum yalnizca WSL runtime destekler.", error=True)
                return

            def resolve_terminal_context(
                spec_terminal_id: str, spec_repo_path: str, spec_branch: str
            ) -> tuple[str, str]:
                repo_name = self._pending_repo_by_terminal.get(spec_terminal_id, "").strip()
                branch_name = self._pending_branch_by_terminal.get(spec_terminal_id, "").strip()

                repo_combo = self._repo_combo_by_terminal.get(spec_terminal_id)
                if repo_combo is not None:
                    selected_repo = repo_combo.currentText().strip()
                    if selected_repo:
                        repo_name = selected_repo

                branch_combo = self._branch_combo_by_terminal.get(spec_terminal_id)
                if branch_combo is not None:
                    selected_branch = branch_combo.currentText().strip()
                    if selected_branch:
                        branch_name = selected_branch

                resolved_repo = spec_repo_path.strip()
                if repo_name:
                    selected_repo = self._repositories_by_name.get(repo_name)
                    if selected_repo is not None:
                        resolved_repo = selected_repo.clone_url
                    elif (
                        repo_name.startswith("/")
                        or "://" in repo_name
                        or repo_name.startswith("git@")
                    ):
                        resolved_repo = repo_name

                resolved_branch = branch_name or spec_branch.strip()
                return resolved_repo, resolved_branch

            wsl_pairs: list[tuple[str, str]] = []
            for item in service.list_instances():
                if item.spec.runtime != RuntimeKind.WSL:
                    continue
                resolved_repo, resolved_branch = resolve_terminal_context(
                    item.spec.terminal_id,
                    item.spec.repo_path,
                    item.spec.branch,
                )
                wsl_pairs.append((resolved_repo, resolved_branch))
            wsl_pairs = [
                (repo_path, branch)
                for repo_path, branch in wsl_pairs
                if repo_path.strip() and branch.strip()
            ]
            selected_wsl_distribution = self._selected_wsl_distribution()
            if not selected_wsl_distribution:
                self._set_status("WSL dagitimi secilmedi.", error=True)
                return
            resolved_workspace_root = _resolve_runtime_workspace_root_wsl(
                selected_wsl_distribution,
                config.default_root,
            )
            workspace_root = _workspace_root_expression(resolved_workspace_root)
            for pane_index, (repo_path, branch) in enumerate(wsl_pairs):
                logger.info(
                    "runtime-open resolved-pane pane=%s repo=%s branch=%s target=%s",
                    pane_index + 1,
                    repo_path,
                    branch,
                    _resolve_wsl_target_path(
                        repo_path,
                        workspace_root=workspace_root,
                        pane_index=pane_index,
                    ),
                )
            if not wsl_pairs:
                service.record_event(
                    terminal_id,
                    "open-skip",
                    "Open skipped: no repo/branch selections for WSL panes.",
                )
                logger.warning(
                    "Open skipped terminal=%s runtime=%s reason=no-wsl-selections",
                    terminal_id,
                    instance.spec.runtime.value,
                )
                self._set_status(
                    "Open icin once en az bir WSL terminalinde repo ve branch secin.",
                    error=True,
                )
                return

            pane_count = max(1, len(wsl_pairs))
            layout_rows = self.grid_rows_spin.value()
            layout_cols = self.grid_cols_spin.value()
            token_value = self.github_token_edit.text().strip()
            has_github_repo = any(
                _github_repo_full_name_from_url(repo_path) for repo_path, _branch in wsl_pairs
            )
            if has_github_repo and not token_value:
                self._set_status(
                    (
                        "GitHub depolari icin GitHub Anahtari gerekli. "
                        "Token girin; baglanti uygulama tarafindan otomatik kurulur."
                    ),
                    error=True,
                )
                return
            summary = ", ".join(f"{repo}@{branch}" for repo, branch in wsl_pairs)
            logger.info(
                "Open request terminal=%s runtime=%s panes=%s layout=%sx%s distro=%s selections=[%s]",
                terminal_id,
                instance.spec.runtime.value,
                pane_count,
                layout_rows,
                layout_cols,
                selected_wsl_distribution,
                summary,
            )
            service.record_event(
                terminal_id,
                "open-start",
                f"Opening {instance.spec.runtime.value} terminal pane_count={pane_count}.",
            )
            self._open_request_terminal_id = terminal_id
            self._open_request_runtime = instance.spec.runtime.value
            self._open_request_pane_count = pane_count
            self._start_open_loading_indicator()
            self._set_status("Terminal aciliyor, hazirlik adimlari baslatiliyor...")

            thread = QThread(self)
            worker = OpenTerminalWorker(
                runtime=instance.spec.runtime,
                pane_count=pane_count,
                layout_rows=layout_rows,
                layout_cols=layout_cols,
                wsl_distribution=selected_wsl_distribution,
                wsl_pairs=wsl_pairs,
                workspace_root_wsl=config.default_root,
                github_token=token_value,
                terminal_font_size=self._terminal_font_size,
            )
            worker.moveToThread(thread)

            thread.started.connect(worker.run)
            worker.succeeded.connect(self._on_open_success)
            worker.progress.connect(self._on_open_progress)
            worker.failed.connect(self._on_open_failed)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._on_open_done)

            self._open_worker = worker
            self._open_thread = thread
            thread.start()

        def _on_open_success(self, payload: object) -> None:
            pane_count = self._open_request_pane_count
            if isinstance(payload, dict):
                candidate = payload.get("pane_count")
                if isinstance(candidate, int) and candidate > 0:
                    pane_count = candidate

            terminal_id = self._open_request_terminal_id
            runtime = self._open_request_runtime
            service.record_event(
                terminal_id,
                "open-success",
                f"External {runtime} terminal launched.",
            )
            logger.info(
                "Open success terminal=%s runtime=%s panes=%s",
                terminal_id,
                runtime,
                pane_count,
            )
            self._set_status(f"{terminal_id} icin {runtime} terminali acildi.")
            self._refresh()

        def _on_open_progress(self, step: str, message: str) -> None:
            terminal_id = self._open_request_terminal_id
            event_step = step.strip() or "open-progress"
            if terminal_id:
                service.record_event(terminal_id, event_step, message)
            self._set_status(message)

        def _on_open_failed(self, kind: str, message: str) -> None:
            terminal_id = self._open_request_terminal_id
            runtime = self._open_request_runtime
            pane_count = self._open_request_pane_count
            if kind == "open-preflight-failed":
                service.record_event(
                    terminal_id,
                    "open-preflight-failed",
                    message,
                )
                logger.error(
                    "runtime-open preflight failed terminal=%s runtime=%s error=%s",
                    terminal_id,
                    runtime,
                    message,
                )
                self._set_status(message, error=True)
                self._refresh()
                return

            service.record_event(
                terminal_id,
                "open-failed",
                f"External {runtime} terminal launch failed.",
            )
            logger.error(
                "Open failed terminal=%s runtime=%s panes=%s",
                terminal_id,
                runtime,
                pane_count,
            )
            self._set_status(f"{terminal_id} icin terminal acilamadi.", error=True)
            self._refresh()

        def _on_open_done(self) -> None:
            self._stop_open_loading_indicator()
            self._open_worker = None
            self._open_thread = None

        def _on_row_repo_changed(self, terminal_id: str) -> None:
            repo_combo = self._repo_combo_by_terminal.get(terminal_id)
            branch_combo = self._branch_combo_by_terminal.get(terminal_id)
            if repo_combo is None or branch_combo is None:
                return
            self._select_row_for_terminal(terminal_id)

            repo_name = repo_combo.currentText().strip()
            self._pending_repo_by_terminal[terminal_id] = repo_name
            self._pending_branch_by_terminal[terminal_id] = ""
            branch_combo.clear()
            if not repo_name:
                return
            branches = self._load_branches_for_repo(repo_name)
            if not branches:
                self._load_branches_async(terminal_id=terminal_id, repo_name=repo_name)
                return

            branch_combo.addItems(branches)
            if branches:
                self._pending_branch_by_terminal[terminal_id] = branches[0]
                self._set_status(f"{repo_name} icin {len(branches)} branch yuklendi.")
                self._apply_auto_switch(terminal_id)

        def _on_row_branch_changed(self, terminal_id: str) -> None:
            branch_combo = self._branch_combo_by_terminal.get(terminal_id)
            if branch_combo is None:
                return
            self._select_row_for_terminal(terminal_id)
            self._pending_branch_by_terminal[terminal_id] = branch_combo.currentText().strip()
            self._apply_auto_switch(terminal_id)

        def _select_row_for_terminal(self, terminal_id: str) -> None:
            if self._updating_table:
                return
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is None:
                    continue
                if item.text().strip() != terminal_id:
                    continue
                self.table.selectRow(row)
                with suppress(BranchNexusError):
                    dashboard.focus_terminal(terminal_id)
                break

        def _apply_auto_switch(self, terminal_id: str) -> None:
            repo_combo = self._repo_combo_by_terminal.get(terminal_id)
            branch_combo = self._branch_combo_by_terminal.get(terminal_id)
            if repo_combo is None or branch_combo is None:
                return
            repo_name = repo_combo.currentText().strip()
            branch = branch_combo.currentText().strip()
            if not repo_name or not branch:
                return
            repo = self._repositories_by_name.get(repo_name)
            if repo is None:
                self._set_status("Depo bilgisi bulunamadi. Repo listesini yenileyin.", error=True)
                return

            instance = next(
                (item for item in service.list_instances() if item.spec.terminal_id == terminal_id),
                None,
            )
            if instance is None:
                self._set_status("Terminal bulunamadi.", error=True)
                return
            if instance.spec.repo_path == repo.clone_url and instance.spec.branch == branch:
                return

            try:
                dashboard.change_repo_branch(
                    terminal_id,
                    repo_path=repo.clone_url,
                    branch=branch,
                )
            except BranchNexusError as exc:
                self._set_status(str(exc), error=True)
                return
            self._pending_repo_by_terminal[terminal_id] = repo_name
            self._pending_branch_by_terminal[terminal_id] = branch
            self._set_status(f"{terminal_id} baglami guncellendi: {repo_name}:{branch}")
            self._refresh()

        def _refresh(self) -> None:
            self._updating_table = True
            try:
                panels_local = dashboard.list_panels()
                self.table.setRowCount(0)
                self._repo_combo_by_terminal.clear()
                self._branch_combo_by_terminal.clear()
                self._apply_table_column_widths()

                repo_names = sorted(self._repositories_by_name.keys(), key=str.lower)
                focus_row = -1

                for row, panel in enumerate(panels_local):
                    self.table.insertRow(row)
                    self.table.setRowHeight(row, self._terminal_row_height)
                    if panel.focused:
                        focus_row = row

                    terminal_item = QTableWidgetItem(panel.terminal_id)
                    self.table.setItem(row, 0, terminal_item)

                    title_widget = QWidget()
                    title_widget.setFixedHeight(self._terminal_cell_height)
                    title_layout = QHBoxLayout(title_widget)
                    title_layout.setContentsMargins(6, 1, 6, 1)
                    title_layout.setSpacing(6)
                    title_label = QLabel(panel.title)
                    title_label.setProperty("row_title_label", True)
                    remove_btn = QPushButton("×")
                    remove_btn.setProperty("danger_btn", True)
                    remove_btn.setToolTip(f"{panel.terminal_id} terminalini kaldir")
                    remove_btn.setFixedSize(28, 28)
                    remove_btn.clicked.connect(
                        lambda _checked=False, terminal_id=panel.terminal_id: (
                            self._remove_terminal_inline(terminal_id)
                        )
                    )
                    title_layout.addWidget(title_label, 1)
                    title_layout.addWidget(remove_btn, 0, Qt.AlignmentFlag.AlignRight)
                    self.table.setCellWidget(row, 1, title_widget)

                    repo_combo = QComboBox()
                    repo_combo.setFixedHeight(self._terminal_cell_height)
                    repo_combo.setProperty("table_row_combo", True)
                    repo_combo.setMinimumContentsLength(20)
                    repo_combo.addItem("")
                    for repo_name in repo_names:
                        repo_combo.addItem(repo_name)

                    selected_repo_name = self._pending_repo_by_terminal.get(panel.terminal_id, "")
                    if not selected_repo_name and panel.repo_path:
                        for repo_name, repo in self._repositories_by_name.items():
                            if repo.clone_url == panel.repo_path:
                                selected_repo_name = repo_name
                                break
                    if selected_repo_name:
                        if repo_combo.findText(selected_repo_name) < 0:
                            repo_combo.addItem(selected_repo_name)
                        repo_combo.setCurrentText(selected_repo_name)

                    branch_combo = QComboBox()
                    branch_combo.setFixedHeight(self._terminal_cell_height)
                    branch_combo.setProperty("table_row_combo", True)
                    branch_combo.setMinimumContentsLength(16)
                    branches: list[str] = []
                    if selected_repo_name:
                        branches = self._branches_by_repo.get(selected_repo_name, [])
                    if branches:
                        branch_combo.addItems(branches)
                    selected_branch = self._pending_branch_by_terminal.get(panel.terminal_id, "")
                    if not selected_branch:
                        selected_branch = panel.branch
                    if selected_branch:
                        if branch_combo.findText(selected_branch) < 0:
                            branch_combo.addItem(selected_branch)
                        branch_combo.setCurrentText(selected_branch)

                    self.table.setCellWidget(row, 2, repo_combo)
                    self.table.setCellWidget(row, 3, branch_combo)
                    self._repo_combo_by_terminal[panel.terminal_id] = repo_combo
                    self._branch_combo_by_terminal[panel.terminal_id] = branch_combo

                    repo_combo.currentIndexChanged.connect(
                        lambda _index, terminal_id=panel.terminal_id: self._on_row_repo_changed(
                            terminal_id
                        )
                    )
                    branch_combo.currentIndexChanged.connect(
                        lambda _index, terminal_id=panel.terminal_id: self._on_row_branch_changed(
                            terminal_id
                        )
                    )

                if focus_row >= 0:
                    self.table.selectRow(focus_row)
            finally:
                self._updating_table = False

            self._select_template_card(dashboard.template_count)
            persist_snapshot()

        def _select_template_card(self, count: int) -> None:
            for template_count, card in self._template_cards.items():
                card.setChecked(template_count == count)

        def _template_preview(self, rows: int, cols: int) -> str:
            # Use pink/magenta squares for the terminal layout preview
            line = " ".join("█" for _ in range(cols))
            return "\n".join(line for _ in range(rows))

        def _apply_visual_style(self) -> None:
            self.setStyleSheet(
                """
                QMainWindow {
                    background: #0f1724;
                }
                QLabel {
                    color: #e5edf7;
                    font-size: 13px;
                }
                QPushButton {
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 8px 16px;
                    color: #e5edf7;
                    font-weight: 500;
                }
                QPushButton:hover {
                    border-color: #60a5fa;
                    background: #243447;
                }
                QPushButton:pressed {
                    background: #1a2634;
                }
                QPushButton:disabled {
                    color: #64748b;
                    background: #141b27;
                    border-color: #1e293b;
                }
                QPushButton[action_btn="true"] {
                    background: #2563eb;
                    border: 1px solid #3b82f6;
                    color: #ffffff;
                    font-weight: 600;
                    padding: 10px 24px;
                    min-width: 100px;
                }
                QPushButton[action_btn="true"]:hover {
                    background: #3b82f6;
                    border-color: #60a5fa;
                }
                QPushButton[action_btn="true"]:pressed {
                    background: #1d4ed8;
                }
                QPushButton[secondary_btn="true"] {
                    background: #1e293b;
                    border: 1px solid #475569;
                    color: #e5edf7;
                    font-weight: 500;
                    padding: 8px 16px;
                    min-width: 120px;
                }
                QPushButton[secondary_btn="true"]:hover {
                    background: #26354a;
                    border-color: #64748b;
                }
                QPushButton[template_card="true"] {
                    text-align: center;
                    padding: 6px;
                    font-family: Consolas, 'Courier New', monospace;
                    font-size: 12px;
                    line-height: 1.2;
                    background: #162032;
                    border: 1px solid #334155;
                    border-radius: 10px;
                    color: #f472b6;
                }
                QPushButton[template_card="true"]:hover {
                    background: #1e293b;
                    border-color: #64748b;
                    color: #f9a8d4;
                }
                QPushButton[template_card="true"]:checked {
                    border: 2px solid #3b82f6;
                    background: #1d2b42;
                    color: #f472b6;
                }
                QPushButton[danger_btn="true"] {
                    background: #2d1f2d;
                    border: 1px solid #78354f;
                    color: #f9a8d4;
                    font-size: 16px;
                    font-weight: 700;
                    padding: 0;
                    min-width: 28px;
                    max-width: 28px;
                    min-height: 28px;
                    max-height: 28px;
                    border-radius: 6px;
                }
                QPushButton[danger_btn="true"]:hover {
                    background: #4a2040;
                    border: 1px solid #d9469a;
                    color: #fce7f3;
                }
                QPushButton[danger_btn="true"]:pressed {
                    background: #3a1830;
                }
                QLabel[row_title_label="true"] {
                    color: #e5edf7;
                    padding-left: 2px;
                }
                QLabel[grid_separator="true"] {
                    color: #9fb4d8;
                    font-weight: 700;
                    padding: 0 2px;
                }
                QLabel[grid_title_label="true"] {
                    color: #b8c8e6;
                    font-size: 12px;
                    font-weight: 600;
                    padding-right: 2px;
                }
                QLineEdit, QComboBox, QSpinBox {
                    background: #0f1724;
                    color: #e5edf7;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 6px 8px;
                    min-height: 30px;
                    selection-background-color: #1d4ed8;
                    selection-color: #ffffff;
                }
                QComboBox QAbstractItemView {
                    background: #0f1724;
                    color: #e5edf7;
                    border: 1px solid #334155;
                    selection-background-color: #1d4ed8;
                    selection-color: #ffffff;
                }
                QComboBox[table_row_combo="true"] {
                    min-height: 0px;
                    padding-top: 2px;
                    padding-bottom: 2px;
                    border-radius: 6px;
                }
                QSpinBox {
                    padding-right: 20px;
                }
                QSpinBox[grid_compact="true"] {
                    min-height: 25px;
                    max-height: 25px;
                    padding-top: 1px;
                    padding-bottom: 1px;
                }
                QSpinBox::up-button, QSpinBox::down-button {
                    background: #182235;
                    border-left: 1px solid #334155;
                    width: 16px;
                }
                QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                    background: #223149;
                }
                QTableWidget {
                    background: #0f1724;
                    color: #e5edf7;
                    border: 1px solid #334155;
                    border-radius: 10px;
                    gridline-color: #263244;
                    selection-background-color: #1d4ed8;
                    selection-color: #ffffff;
                }
                QTableWidget::item {
                    color: #e5edf7;
                }
                QHeaderView::section {
                    background: #1a2230;
                    color: #e5edf7;
                    border: none;
                    border-right: 1px solid #334155;
                    padding: 8px;
                    font-weight: 600;
                }
                """
            )

        def closeEvent(self, event) -> None:  # type: ignore[override]
            persist_snapshot()
            event.accept()

    app = QApplication.instance() or QApplication(sys.argv)  # pragma: no cover
    window = RuntimeDashboardWindow()  # pragma: no cover
    window.show()
    app.exec()  # pragma: no cover
    persist_snapshot()  # pragma: no cover
    return int(ExitCode.SUCCESS)  # pragma: no cover


def launch_app(
    *,
    config_path: str | Path | None = None,
    fresh_start: bool = False,
) -> int:
    logger.debug("Launching GUI application")
    config = load_config(config_path)
    if fresh_start:
        logger.info("runtime-open fresh-start request source=cli")
        _run_fresh_start_reset(config=config, config_path=config_path)
    state = build_state_from_config(config)
    logger.info(
        "runtime-v2 startup decision enabled=%s source=%s forced_on=%s", True, "runtime-only", False
    )
    return launch_runtime_dashboard(
        config=config, state=state, config_path=config_path, run_ui=True
    )
