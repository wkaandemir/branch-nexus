from __future__ import annotations

import branchnexus.ui.app as app_module
import branchnexus.ui.runtime.bootstrap as bootstrap


def test_build_runtime_wsl_bootstrap_command_uses_home_workspace_for_non_wsl_root() -> None:
    command = bootstrap.build_runtime_wsl_bootstrap_command(
        pane_count=2,
        repo_branch_pairs=[("https://github.com/org/repo.git", "main")],
        workspace_root_wsl=r"C:\repos",
    )
    assert 'mkdir -p "$HOME/branchnexus-workspace/repo"' in command
    assert 'cd "$HOME/branchnexus-workspace/repo/pane-1"' in command
    assert "tmux set-option -t branchnexus-runtime mouse on" in command


def test_build_runtime_wsl_attach_command_uses_prepared_paths() -> None:
    command = bootstrap.build_runtime_wsl_attach_command(
        pane_paths=["/work/root/repo/pane-1-main", "/work/root/repo/pane-2-feature"]
    )
    assert "tmux new-session -d -s branchnexus-runtime -c /work/root/repo/pane-1-main" in command
    assert "tmux split-window -t branchnexus-runtime -c /work/root/repo/pane-2-feature" in command
    assert "tmux attach-session -t branchnexus-runtime" in command


def test_build_runtime_wait_open_commands_without_progress_log() -> None:
    commands = bootstrap.build_runtime_wait_open_commands(
        distribution="Ubuntu-20.04",
        session_name="branchnexus-runtime",
    )
    assert commands[0][0][0] == "wsl.exe"
    assert "progress_log=/tmp/branchnexus-open-progress.log" in commands[0][0][6]
    assert "tmux attach-session -t branchnexus-runtime" in commands[0][0][6]


def test_prepare_runtime_wsl_failure_session_forwards_to_app(monkeypatch) -> None:
    called: list[str] = []

    def fake_prepare_runtime_wsl_failure_session(**kwargs: object) -> None:
        called.append(str(kwargs.get("message", "")))

    monkeypatch.setattr(
        app_module,
        "prepare_runtime_wsl_failure_session",
        fake_prepare_runtime_wsl_failure_session,
    )
    bootstrap.prepare_runtime_wsl_failure_session(
        distribution="Ubuntu",
        message="boom",
    )
    assert called == ["boom"]
