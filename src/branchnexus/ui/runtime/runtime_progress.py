"""Runtime progress logging and event formatting."""

from __future__ import annotations

import logging as py_logging
import os
import shlex
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import PurePosixPath

from branchnexus.runtime.wsl_discovery import build_wsl_command
from branchnexus.ui.runtime.constants import WSL_PROGRESS_LOG_IO_TIMEOUT_SECONDS
from branchnexus.ui.services.security import sanitize_terminal_log_text
from branchnexus.ui.services.wsl_runner import background_subprocess_kwargs
from branchnexus.ui.widgets.runtime_output import RuntimeOutputPanel

logger = py_logging.getLogger(__name__)


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
    detail = sanitize_terminal_log_text(message)
    return f"[BranchNexus][{stamp}][{level}] {step_name}: {detail}"


def emit_terminal_progress(
    sink: Callable[[str], None] | None,
    *,
    level: str,
    step: str,
    message: str,
) -> None:
    if sink is None:
        return
    sink(_format_terminal_progress_line(level, step, message))


def build_runtime_progress_log_path(workspace_root_wsl: str) -> str:
    root = workspace_root_wsl.replace("\ufeff", "").replace("\x00", "").strip().rstrip("/")
    if not root.startswith("/"):
        return ""
    return f"{root}/.bnx/runtime/open-progress.log"


def init_wsl_progress_log(
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
            timeout=WSL_PROGRESS_LOG_IO_TIMEOUT_SECONDS,
            **background_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.debug("runtime-open progress-log-init failed path=%s", path, exc_info=True)


def append_wsl_progress_log(
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
            timeout=WSL_PROGRESS_LOG_IO_TIMEOUT_SECONDS,
            **background_subprocess_kwargs(),
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.debug("runtime-open progress-log-append failed path=%s", path, exc_info=True)
