"""GUI shell and runtime dashboard orchestration flow."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from branchnexus.config import load_config
from branchnexus.ui.runtime import legacy_app_impl as _legacy

Toast = _legacy.Toast
WizardRouter = _legacy.WizardRouter
AppShell = _legacy.AppShell
WizardSelections = _legacy.WizardSelections

build_state_from_config = _legacy.build_state_from_config
apply_wizard_selections = _legacy.apply_wizard_selections
selection_errors = _legacy.selection_errors
build_orchestration_request = _legacy.build_orchestration_request
format_runtime_events = _legacy.format_runtime_events
tmux_shortcuts_lines = _legacy.tmux_shortcuts_lines
_dedupe = _legacy._dedupe

# Runtime-related exports used by tests and command orchestration.
select_runtime_wsl_distribution = _legacy.select_runtime_wsl_distribution
prepare_wsl_runtime_pane_paths = _legacy.prepare_wsl_runtime_pane_paths
build_runtime_wsl_bootstrap_command = _legacy.build_runtime_wsl_bootstrap_command
build_runtime_wsl_attach_command = _legacy.build_runtime_wsl_attach_command
build_runtime_wait_open_commands = _legacy.build_runtime_wait_open_commands
open_runtime_waiting_terminal = _legacy.open_runtime_waiting_terminal
reset_runtime_wsl_session = _legacy.reset_runtime_wsl_session
prepare_runtime_wsl_attach_session = _legacy.prepare_runtime_wsl_attach_session
prepare_runtime_wsl_failure_session = _legacy.prepare_runtime_wsl_failure_session
build_terminal_launch_commands = _legacy.build_terminal_launch_commands
launch_tmux_terminal = _legacy.launch_tmux_terminal
build_runtime_open_commands = _legacy.build_runtime_open_commands
open_runtime_terminal = _legacy.open_runtime_terminal
launch_runtime_dashboard = _legacy.launch_runtime_dashboard
_run_fresh_start_reset = _legacy._run_fresh_start_reset


def launch_app(
    *,
    config_path: str | Path | None = None,
    fresh_start: bool = False,
) -> int:
    """Launch the runtime dashboard from persisted config."""
    config = load_config(config_path)
    if fresh_start:
        _run_fresh_start_reset(config=config, config_path=config_path)
    state = build_state_from_config(config)
    return launch_runtime_dashboard(
        config=config,
        state=state,
        config_path=config_path,
        run_ui=True,
    )


def __getattr__(name: str) -> Any:
    """Fallback export bridge for legacy private/runtime helpers."""
    try:
        return getattr(_legacy, name)
    except AttributeError as exc:  # pragma: no cover - import edge path
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
