"""Runtime bootstrap and attach command helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import cast


def prepare_wsl_runtime_pane_paths(
    *,
    distribution: str,
    repo_branch_pairs: list[tuple[str, str]],
    workspace_root_wsl: str,
    github_token: str = "",
    progress: Callable[[str, str], None] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> list[str]:
    from branchnexus.ui import app as app_module

    return app_module.prepare_wsl_runtime_pane_paths(
        distribution=distribution,
        repo_branch_pairs=repo_branch_pairs,
        workspace_root_wsl=workspace_root_wsl,
        github_token=github_token,
        progress=progress,
        verbose_sink=verbose_sink,
    )


def build_runtime_wsl_bootstrap_command(
    *,
    pane_count: int,
    repo_branch_pairs: list[tuple[str, str]] | None = None,
    workspace_root_wsl: str = "",
    session_name: str = "branchnexus-runtime",
    layout_rows: int | None = None,
    layout_cols: int | None = None,
) -> str:
    from branchnexus.ui import app as app_module

    return app_module.build_runtime_wsl_bootstrap_command(
        pane_count=pane_count,
        repo_branch_pairs=repo_branch_pairs,
        workspace_root_wsl=workspace_root_wsl,
        session_name=session_name,
        layout_rows=layout_rows,
        layout_cols=layout_cols,
    )


def build_runtime_wsl_attach_command(
    *,
    pane_paths: list[str],
    session_name: str = "branchnexus-runtime",
    layout_rows: int | None = None,
    layout_cols: int | None = None,
) -> str:
    from branchnexus.ui import app as app_module

    return app_module.build_runtime_wsl_attach_command(
        pane_paths=pane_paths,
        session_name=session_name,
        layout_rows=layout_rows,
        layout_cols=layout_cols,
    )


def build_runtime_wait_open_commands(
    *,
    distribution: str,
    session_name: str = "branchnexus-runtime",
    progress_log_path: str = "",
) -> list[tuple[list[str], int]]:
    from branchnexus.ui import app as app_module

    return app_module.build_runtime_wait_open_commands(
        wsl_distribution=distribution,
        session_name=session_name,
        progress_log_path=progress_log_path,
    )


def open_runtime_waiting_terminal(
    *,
    distribution: str,
    session_name: str = "branchnexus-runtime",
    progress_log_path: str = "",
) -> bool:
    from branchnexus.ui import app as app_module

    return app_module.open_runtime_waiting_terminal(
        wsl_distribution=distribution,
        session_name=session_name,
        progress_log_path=progress_log_path,
    )


def reset_runtime_wsl_session(
    *,
    distribution: str,
    session_name: str = "branchnexus-runtime",
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> None:
    from branchnexus.ui import app as app_module

    return app_module.reset_runtime_wsl_session(
        distribution=distribution,
        session_name=session_name,
        env=env,
        verbose_sink=verbose_sink,
    )


def prepare_runtime_wsl_attach_session(
    *,
    distribution: str,
    pane_paths: list[str],
    session_name: str = "branchnexus-runtime",
    env: dict[str, str] | None = None,
    verbose_sink: Callable[[str], None] | None = None,
) -> None:
    from branchnexus.ui import app as app_module

    return app_module.prepare_runtime_wsl_attach_session(
        distribution=distribution,
        pane_paths=pane_paths,
        session_name=session_name,
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
    from branchnexus.ui import app as app_module

    return app_module.prepare_runtime_wsl_failure_session(
        distribution=distribution,
        message=message,
        session_name=session_name,
        env=env,
        verbose_sink=verbose_sink,
    )


def _build_wsl_pane_context_command(
    *,
    pane_path: str,
    pane_index: int,
    layout_name: str,
) -> str:
    from branchnexus.ui import app as app_module

    return cast(
        str,
        app_module._build_wsl_pane_context_command(
        pane_path=pane_path,
        pane_index=pane_index,
        layout_name=layout_name,
        ),
    )


def _build_wsl_pane_startup_command(
    *,
    pane_path: str,
    pane_index: int,
    layout_name: str,
) -> str:
    from branchnexus.ui import app as app_module

    return cast(
        str,
        app_module._build_wsl_pane_startup_command(
        pane_path=pane_path,
        pane_index=pane_index,
        layout_name=layout_name,
        ),
    )


def _build_runtime_wsl_wait_script(*, session_name: str, progress_log_path: str = "") -> str:
    from branchnexus.ui import app as app_module

    return cast(
        str,
        app_module._build_runtime_wsl_wait_script(
            session_name=session_name,
            progress_log_path=progress_log_path,
        ),
    )


def _runtime_interactive_shell_entry() -> str:
    from branchnexus.ui import app as app_module

    return cast(str, app_module._runtime_interactive_shell_entry())


def _runtime_tmux_style_commands(session_name: str) -> list[str]:
    from branchnexus.ui import app as app_module

    return cast(list[str], app_module._runtime_tmux_style_commands(session_name))


def _runtime_tmux_resize_hook_commands(session_name: str, layout_name: str) -> list[str]:
    from branchnexus.ui import app as app_module

    return cast(
        list[str],
        app_module._runtime_tmux_resize_hook_commands(session_name, layout_name),
    )


def _resolve_runtime_grid_dimensions(
    pane_count: int,
    *,
    rows: int | None = None,
    cols: int | None = None,
) -> tuple[int, int]:
    from branchnexus.ui import app as app_module

    return cast(
        tuple[int, int],
        app_module._resolve_runtime_grid_dimensions(
            pane_count=pane_count,
            rows=rows,
            cols=cols,
        ),
    )


def _tmux_layout_name_for_grid(rows: int, cols: int) -> str:
    from branchnexus.ui import app as app_module

    return cast(str, app_module._tmux_layout_name_for_grid(rows, cols))
