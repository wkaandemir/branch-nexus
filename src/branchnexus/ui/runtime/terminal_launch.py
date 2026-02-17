"""Terminal launch helpers for tmux and runtime sessions."""

from __future__ import annotations

import logging as py_logging
import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from branchnexus.runtime.wsl_discovery import build_wsl_command
from branchnexus.terminal import RuntimeKind
from branchnexus.ui.runtime.runtime_progress import _dedupe
from branchnexus.ui.runtime.runtime_tmux import (
    build_runtime_wait_open_commands,
    build_runtime_wsl_attach_command,
    build_runtime_wsl_bootstrap_command,
)
from branchnexus.ui.services.security import command_for_log

logger = py_logging.getLogger(__name__)


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
            command_for_log(command),
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
        creation_flags = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        commands: list[tuple[list[str], int]] = [(shell_command, creation_flags)]
        logger.debug(
            "runtime-open command-candidates runtime=%s count=%s", runtime.value, len(commands)
        )
        return commands
    else:
        shell_command = ["powershell.exe", "-NoLogo", "-NoProfile"]
    commands = []
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
            command_for_log(command),
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
