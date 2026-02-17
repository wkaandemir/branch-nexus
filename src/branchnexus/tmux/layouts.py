"""Tmux layout strategy for 2-6 panes."""

from __future__ import annotations

from dataclasses import dataclass

from branchnexus.errors import BranchNexusError, ExitCode


@dataclass(frozen=True)
class PaneTarget:
    pane_index: int
    worktree_path: str


_VALID_LAYOUTS = {"horizontal", "vertical", "grid"}


def validate_layout(layout: str, panes: int) -> None:
    if layout not in _VALID_LAYOUTS:
        raise BranchNexusError(
            f"Unsupported layout: {layout}",
            code=ExitCode.VALIDATION_ERROR,
            hint="Use horizontal, vertical, or grid.",
        )
    if panes < 2 or panes > 6:
        raise BranchNexusError(
            f"Invalid pane count: {panes}",
            code=ExitCode.VALIDATION_ERROR,
            hint="Use a pane value between 2 and 6.",
        )


def build_layout_commands(
    *,
    session_name: str,
    layout: str,
    pane_paths: list[str],
) -> list[list[str]]:
    panes = len(pane_paths)
    validate_layout(layout, panes)

    commands: list[list[str]] = [
        ["tmux", "new-session", "-d", "-s", session_name, "-c", pane_paths[0]],
        ["tmux", "set-option", "-t", session_name, "mouse", "on"],
        ["tmux", "bind-key", "-n", "WheelUpPane", "send-keys", "-M"],
        ["tmux", "bind-key", "-n", "WheelDownPane", "send-keys", "-M"],
    ]

    for index in range(1, panes):
        if layout == "horizontal":
            split_flag = "-h"
        elif layout == "vertical":
            split_flag = "-v"
        else:
            split_flag = "-h" if index % 2 else "-v"
        commands.append(
            [
                "tmux",
                "split-window",
                split_flag,
                "-t",
                f"{session_name}:0",
                "-c",
                pane_paths[index],
            ]
        )

    if layout == "horizontal":
        tmux_layout = "even-horizontal"
    elif layout == "vertical":
        tmux_layout = "even-vertical"
    else:
        tmux_layout = "tiled"

    commands.append(["tmux", "select-layout", "-t", f"{session_name}:0", tmux_layout])
    commands.append(
        [
            "tmux",
            "set-hook",
            "-t",
            session_name,
            "client-resized",
            f"select-layout -t {session_name}:0 {tmux_layout}",
        ]
    )
    commands.append(["tmux", "select-pane", "-t", f"{session_name}:0.0"])
    return commands


def map_pane_targets(pane_paths: list[str]) -> list[PaneTarget]:
    return [PaneTarget(pane_index=index, worktree_path=path) for index, path in enumerate(pane_paths)]
