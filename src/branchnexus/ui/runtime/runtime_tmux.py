"""Runtime tmux session and pane command building."""

from __future__ import annotations

import logging as py_logging
import os
import shlex
import subprocess
from collections.abc import Callable

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.git.remote_workspace import repo_name_from_url
from branchnexus.runtime.wsl_discovery import build_wsl_command
from branchnexus.ui.runtime.constants import DEFAULT_WSL_PROGRESS_LOG_PATH
from branchnexus.ui.runtime.runtime_progress import emit_terminal_progress
from branchnexus.ui.runtime.wsl_preflight import (
    _sanitize_repo_segment,
    _workspace_root_expression,
    _resolve_wsl_target_path,
)
from branchnexus.ui.services.github_env import github_token_tmux_env_script
from branchnexus.ui.services.security import command_for_log, truncate_log
from branchnexus.ui.services.wsl_runner import background_subprocess_kwargs

logger = py_logging.getLogger(__name__)


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
        truncate_log(result),
    )
    return result


def _runtime_interactive_shell_entry() -> str:
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
        truncate_log(startup),
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
        github_token_tmux_env_script(),
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
    logger.debug("runtime-open bootstrap-command=%s", truncate_log(bootstrap, limit=1400))
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
    logger.debug("runtime-open attach-command=%s", truncate_log(bootstrap, limit=1200))
    return bootstrap


def _build_runtime_wsl_wait_script(*, session_name: str, progress_log_path: str = "") -> str:
    resolved_progress_log = progress_log_path.strip() or DEFAULT_WSL_PROGRESS_LOG_PATH
    default_progress_log = shlex.quote(DEFAULT_WSL_PROGRESS_LOG_PATH)
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


def _run_runtime_wsl_tmux_script(
    *,
    distribution: str,
    script: str,
    step: str,
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> None:
    command = build_wsl_command(distribution, ["bash", "-lc", script])
    logger.debug("runtime-open tmux-run step=%s command=%s", step, command_for_log(command))
    emit_terminal_progress(
        verbose_sink,
        level="RUN",
        step=step,
        message=f"command={command_for_log(command)}",
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
        **background_subprocess_kwargs(),
    )
    if result.returncode == 0:
        logger.debug(
            "runtime-open tmux-ok step=%s stdout=%s", step, truncate_log(result.stdout)
        )
        emit_terminal_progress(
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
        truncate_log(result.stderr),
    )
    emit_terminal_progress(
        verbose_sink,
        level="FAIL",
        step=step,
        message=f"code={result.returncode} stderr={truncate_log(result.stderr, limit=220)}",
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
