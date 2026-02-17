"""End-to-end orchestration from runtime selections to tmux session."""

from __future__ import annotations

import logging as py_logging
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.git.materialize import materialize_remote_branch
from branchnexus.runtime.wsl_discovery import build_wsl_command, validate_distribution
from branchnexus.tmux.bootstrap import ensure_tmux
from branchnexus.tmux.layouts import build_layout_commands
from branchnexus.ui.widgets.runtime_output import RuntimeOutputPanel
from branchnexus.worktree.manager import (
    ManagedWorktree,
    SubprocessRunner,
    WorktreeAssignment,
    WorktreeManager,
)

logger = py_logging.getLogger(__name__)


class OrchestrationRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    distribution: str
    available_distributions: list[str]
    layout: str
    cleanup_policy: str
    assignments: list[WorktreeAssignment]
    worktree_base: Path | PurePosixPath
    session_name: str = "branchnexus"
    tmux_auto_install: bool = True


@dataclass
class OrchestrationResult:
    worktrees: list[ManagedWorktree]
    executed_commands: list[list[str]]


def orchestrate(
    request: OrchestrationRequest,
    *,
    runner: SubprocessRunner = subprocess.run,
    output: RuntimeOutputPanel | None = None,
    manager: WorktreeManager | None = None,
) -> OrchestrationResult:
    panel = output or RuntimeOutputPanel()
    logger.debug(
        "Starting orchestration distribution=%s layout=%s cleanup=%s panes=%s",
        request.distribution,
        request.layout,
        request.cleanup_policy,
        len(request.assignments),
    )

    if not validate_distribution(request.distribution, request.available_distributions):
        logger.error("Invalid WSL distribution selected: %s", request.distribution)
        raise BranchNexusError(
            f"Invalid WSL distribution: {request.distribution}",
            code=ExitCode.RUNTIME_ERROR,
            hint="Re-open WSL selection and choose a discovered distribution.",
        )

    panel.record_started("tmux-bootstrap", "Checking tmux availability")
    logger.debug("Checking tmux availability in distribution=%s", request.distribution)
    ensure_tmux(request.distribution, auto_install=request.tmux_auto_install, runner=runner)
    panel.record_success("tmux-bootstrap", "tmux is available")
    logger.debug("tmux available in distribution=%s", request.distribution)

    worktree_manager = manager or WorktreeManager(request.worktree_base, request.cleanup_policy)
    executed: list[list[str]] = []

    def wsl_runner(
        command: list[str],
        *,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        wrapped = build_wsl_command(request.distribution, command)
        executed.append(wrapped)
        logger.debug("Running command via WSL: %s", wrapped)
        return runner(
            wrapped,
            capture_output=capture_output,
            text=text,
            check=check,
        )

    normalized_assignments: list[WorktreeAssignment] = []
    panel.record_started("branch-materialize", "Preparing selected remote branches")
    for assignment in sorted(request.assignments, key=lambda item: item.pane):
        local_branch = assignment.branch
        if assignment.branch.startswith("origin/"):
            logger.debug(
                "Materializing remote branch pane=%s repo=%s branch=%s",
                assignment.pane,
                assignment.repo_path,
                assignment.branch,
            )
            local_branch = materialize_remote_branch(
                assignment.repo_path,
                assignment.branch,
                runner=wsl_runner,
            )
        normalized_assignments.append(
            WorktreeAssignment(
                pane=assignment.pane,
                repo_path=assignment.repo_path,
                branch=local_branch,
            )
        )
    panel.record_success("branch-materialize", "Remote branches are ready")
    logger.debug("Prepared %s pane assignments", len(normalized_assignments))

    worktrees: list[ManagedWorktree] = []
    try:
        panel.record_started("worktree", "Creating worktrees for pane assignments")
        worktrees = worktree_manager.materialize(
            normalized_assignments,
            runner=wsl_runner,  # type: ignore[arg-type]
        )
        panel.record_success("worktree", f"Created {len(worktrees)} worktrees")
        logger.debug("Created %s worktrees", len(worktrees))

        pane_paths = [str(item.path) for item in sorted(worktrees, key=lambda item: item.pane)]
        tmux_commands = build_layout_commands(
            session_name=request.session_name,
            layout=request.layout,
            pane_paths=pane_paths,
        )

        panel.record_started("tmux-layout", "Starting tmux session")

        def run_tmux_command(command: list[str]) -> tuple[list[str], subprocess.CompletedProcess[str]]:
            wrapped = build_wsl_command(request.distribution, command)
            logger.debug("Executing tmux command: %s", wrapped)
            result = runner(wrapped, capture_output=True, text=True, check=False)
            executed.append(wrapped)
            return wrapped, result

        for command in tmux_commands:
            wrapped, result = run_tmux_command(command)
            if result.returncode != 0:
                stderr = result.stderr.strip()
                is_duplicate_new_session = (
                    command[:2] == ["tmux", "new-session"] and "duplicate session" in stderr.lower()
                )
                if is_duplicate_new_session:
                    logger.warning(
                        "tmux session already exists session=%s; replacing existing session",
                        request.session_name,
                    )
                    _, kill_result = run_tmux_command(["tmux", "kill-session", "-t", request.session_name])
                    if kill_result.returncode == 0:
                        wrapped, result = run_tmux_command(command)
                        stderr = result.stderr.strip()
                    else:
                        kill_error = kill_result.stderr.strip() or "tmux kill-session failed"
                        stderr = f"{stderr}; cleanup failed: {kill_error}" if stderr else kill_error

                if result.returncode == 0:
                    continue

                panel.record_error("tmux-layout", stderr or "tmux command failed")
                logger.error(
                    "tmux command failed command=%s stderr=%s",
                    wrapped,
                    stderr,
                )
                raise BranchNexusError(
                    "Failed to initialize tmux session.",
                    code=ExitCode.TMUX_ERROR,
                    hint=stderr or "Inspect tmux output and retry.",
                )

        panel.record_success("tmux-layout", "tmux session ready")
        logger.debug("Orchestration finished successfully")
        return OrchestrationResult(worktrees=worktrees, executed_commands=executed)
    except Exception:
        if worktrees:
            try:
                removed = worktree_manager.cleanup(
                    runner=wsl_runner,  # type: ignore[arg-type]
                    selected=worktrees,
                    ignore_policy=True,
                )
                logger.warning("Orchestration rollback removed %s worktrees", len(removed))
            except BranchNexusError as cleanup_error:
                logger.error("Orchestration rollback cleanup failed: %s", cleanup_error)
        raise
