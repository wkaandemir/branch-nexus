"""Wizard UI models and helpers for runtime configuration."""

from __future__ import annotations

import logging as py_logging
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, field_validator

from branchnexus.config import AppConfig
from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.git.remote_workspace import (
    ensure_remote_repo_synced,
    list_remote_branches_in_repo,
    resolve_wsl_home_directory,
)
from branchnexus.orchestrator import OrchestrationRequest
from branchnexus.presets import resolve_terminal_template
from branchnexus.runtime.wsl_discovery import to_wsl_path
from branchnexus.ui.state import AppState
from branchnexus.worktree.manager import WorktreeAssignment

logger = py_logging.getLogger(__name__)


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
