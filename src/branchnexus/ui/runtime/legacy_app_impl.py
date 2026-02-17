"""GUI shell and runtime dashboard orchestration flow."""

from __future__ import annotations

import logging as py_logging
from pathlib import Path

from branchnexus.config import load_config
from branchnexus.ui.services.session_manager import _run_fresh_start_reset
from branchnexus.ui.state import AppState

from branchnexus.ui.runtime.dashboard_window import launch_runtime_dashboard
from branchnexus.ui.runtime.runtime_progress import (
    _dedupe,
    format_runtime_events,
    tmux_shortcuts_lines,
)
from branchnexus.ui.runtime.runtime_tmux import (
    build_runtime_wait_open_commands,
    build_runtime_wsl_attach_command,
    build_runtime_wsl_bootstrap_command,
    prepare_runtime_wsl_attach_session,
    prepare_runtime_wsl_failure_session,
    reset_runtime_wsl_session,
)
from branchnexus.ui.runtime.terminal_launch import (
    build_runtime_open_commands,
    build_terminal_launch_commands,
    launch_tmux_terminal,
    open_runtime_terminal,
    open_runtime_waiting_terminal,
)
from branchnexus.ui.runtime.wsl_preflight import (
    prepare_wsl_runtime_pane_paths,
    select_runtime_wsl_distribution,
)
from branchnexus.ui.runtime.wizard_models import (
    AppShell,
    Toast,
    WizardRouter,
    WizardSelections,
    apply_wizard_selections,
    build_orchestration_request,
    build_state_from_config,
    selection_errors,
)

logger = py_logging.getLogger(__name__)


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
