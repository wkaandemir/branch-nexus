from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.tmux.layouts import build_layout_commands, map_pane_targets


@pytest.mark.parametrize("layout", ["horizontal", "vertical", "grid"])
@pytest.mark.parametrize("panes", [2, 3, 4, 5, 6])
def test_layout_commands_for_each_valid_size(layout: str, panes: int) -> None:
    paths = [f"/tmp/w{i}" for i in range(panes)]
    commands = build_layout_commands(session_name="bnx", layout=layout, pane_paths=paths)
    if layout == "horizontal":
        expected_layout = "even-horizontal"
    elif layout == "vertical":
        expected_layout = "even-vertical"
    else:
        expected_layout = "tiled"
    assert commands[0][:3] == ["tmux", "new-session", "-d"]
    assert ["tmux", "set-option", "-t", "bnx", "mouse", "on"] in commands
    assert ["tmux", "bind-key", "-n", "WheelUpPane", "send-keys", "-M"] in commands
    assert ["tmux", "bind-key", "-n", "WheelDownPane", "send-keys", "-M"] in commands
    assert ["tmux", "select-layout", "-t", "bnx:0", expected_layout] in commands
    assert [
        "tmux",
        "set-hook",
        "-t",
        "bnx",
        "client-resized",
        f"select-layout -t bnx:0 {expected_layout}",
    ] in commands
    assert commands[-1][:2] == ["tmux", "select-pane"]


def test_invalid_panes_rejected() -> None:
    with pytest.raises(BranchNexusError):
        build_layout_commands(session_name="bnx", layout="grid", pane_paths=["/tmp/one"])


def test_pane_target_mapping() -> None:
    targets = map_pane_targets(["/a", "/b"])
    assert [(t.pane_index, t.worktree_path) for t in targets] == [(0, "/a"), (1, "/b")]
