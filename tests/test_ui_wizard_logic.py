from __future__ import annotations

from pathlib import PurePosixPath

from branchnexus.config import AppConfig
from branchnexus.terminal import RuntimeKind
from branchnexus.ui.app import (
    WizardSelections,
    apply_wizard_selections,
    build_orchestration_request,
    build_runtime_open_commands,
    build_runtime_wait_open_commands,
    build_runtime_wsl_attach_command,
    build_runtime_wsl_bootstrap_command,
    build_state_from_config,
    build_terminal_launch_commands,
    format_runtime_events,
    select_runtime_wsl_distribution,
    selection_errors,
    tmux_shortcuts_lines,
)
from branchnexus.ui.widgets.runtime_output import RuntimeOutputPanel


def test_build_state_from_config_uses_defaults() -> None:
    config = AppConfig(
        default_root="/repos",
        remote_repo_url="https://github.com/org/repo.git",
        default_layout="vertical",
        default_panes=5,
        cleanup_policy="persistent",
        wsl_distribution="Ubuntu",
    )

    state = build_state_from_config(config)
    assert state.root_path == "/repos"
    assert state.remote_repo_url == "https://github.com/org/repo.git"
    assert state.layout == "vertical"
    assert state.panes == 5
    assert state.cleanup == "persistent"
    assert state.wsl_distribution == "Ubuntu"


def test_apply_wizard_selections_updates_all_user_settings() -> None:
    config = AppConfig()
    state = build_state_from_config(config)
    selections = WizardSelections(
        root_path="C:/src",
        repo_url="https://github.com/org/repo.git",
        github_token="ghp_testtoken",
        repo_path_wsl="/mnt/c/src/repo",
        layout="grid",
        panes=2,
        cleanup="session",
        wsl_distribution="Debian",
        tmux_auto_install=False,
        assignments={
            1: ("/mnt/c/src/repo", "origin/main"),
            2: ("/mnt/c/src/repo", "origin/feature"),
        },
    )

    apply_wizard_selections(config=config, state=state, selections=selections)

    assert state.root_path == "C:/src"
    assert state.remote_repo_url == "https://github.com/org/repo.git"
    assert state.layout == "grid"
    assert state.panes == 2
    assert state.cleanup == "session"
    assert state.wsl_distribution == "Debian"
    assert state.assignments[1] == ("/mnt/c/src/repo", "origin/main")
    assert len(state.assignments) == 2

    assert config.default_root == "C:/src"
    assert config.remote_repo_url == "https://github.com/org/repo.git"
    assert config.github_token == "ghp_testtoken"
    assert config.default_layout == "grid"
    assert config.default_panes == 2
    assert config.cleanup_policy == "session"
    assert config.wsl_distribution == "Debian"
    assert config.tmux_auto_install is False


def test_selection_errors_detect_missing_mouse_selections() -> None:
    selections = WizardSelections(
        root_path="",
        repo_url="",
        repo_path_wsl="",
        layout="grid",
        panes=3,
        cleanup="session",
        wsl_distribution="",
        tmux_auto_install=True,
        assignments={1: ("/mnt/c/repos/repo", "origin/main")},
    )

    errors = selection_errors(selections)
    assert any("repo" in item.lower() for item in errors)
    assert any("WSL" in item for item in errors)
    assert any("panel" in item.lower() for item in errors)


def test_selection_errors_pass_for_complete_settings() -> None:
    selections = WizardSelections(
        root_path="C:/repos",
        repo_url="https://github.com/org/repo.git",
        repo_path_wsl="/mnt/c/repos/repo",
        layout="horizontal",
        panes=2,
        cleanup="persistent",
        wsl_distribution="Ubuntu",
        tmux_auto_install=True,
        assignments={
            1: ("/mnt/c/repos/repo", "origin/main"),
            2: ("/mnt/c/repos/repo", "origin/feature"),
        },
    )

    assert selection_errors(selections) == []


def test_build_orchestration_request_converts_host_paths_and_validates_branches() -> None:
    selections = WizardSelections(
        root_path=r"C:\Users\demo\repos",
        repo_url="https://github.com/org/repo.git",
        repo_path_wsl="",
        layout="grid",
        panes=2,
        cleanup="session",
        wsl_distribution="Ubuntu",
        tmux_auto_install=False,
        assignments={
            1: ("/mnt/c/Users/demo/repos/repo", "origin/main"),
            2: ("/mnt/c/Users/demo/repos/repo", "origin/feature"),
        },
    )

    def converter(distribution: str, host_path: str) -> str:
        assert distribution == "Ubuntu"
        return host_path.replace(r"C:\Users\demo", "/mnt/c/Users/demo").replace("\\", "/")

    def sync_repo(**kwargs: object) -> PurePosixPath:
        assert kwargs["repo_url"] == "https://github.com/org/repo.git"
        return PurePosixPath("/mnt/c/Users/demo/repos/repo")

    def branch_loader(**kwargs: object) -> list[str]:
        return ["origin/main", "origin/feature"]

    request = build_orchestration_request(
        selections,
        ["Ubuntu"],
        path_converter=converter,
        repo_sync=sync_repo,
        branch_loader=branch_loader,
    )
    assert request.distribution == "Ubuntu"
    assert request.tmux_auto_install is False
    assert str(request.worktree_base).startswith("/mnt/c/Users/demo/repos")
    assert str(request.assignments[0].repo_path).startswith("/mnt/c/Users/demo/repos")
    assert request.assignments[0].branch == "origin/main"


def test_build_orchestration_request_uses_wsl_home_when_root_empty() -> None:
    selections = WizardSelections(
        root_path="",
        repo_url="https://github.com/org/repo.git",
        repo_path_wsl="",
        layout="grid",
        panes=2,
        cleanup="session",
        wsl_distribution="Ubuntu",
        tmux_auto_install=True,
        assignments={1: ("", "origin/main"), 2: ("", "origin/feature")},
    )

    def home_resolver(**kwargs: object) -> PurePosixPath:
        assert kwargs["distribution"] == "Ubuntu"
        return PurePosixPath("/home/demo")

    def sync_repo(**kwargs: object) -> PurePosixPath:
        assert kwargs["workspace_root_wsl"] == "/home/demo"
        return PurePosixPath("/home/demo/repo")

    def branch_loader(**kwargs: object) -> list[str]:
        return ["origin/main", "origin/feature"]

    request = build_orchestration_request(
        selections,
        ["Ubuntu"],
        home_resolver=home_resolver,
        repo_sync=sync_repo,
        branch_loader=branch_loader,
    )
    assert str(request.worktree_base) == "/home/demo/.branchnexus-worktrees"
    assert str(request.assignments[0].repo_path) == "/home/demo/repo"


def test_build_orchestration_request_supports_repo_per_pane() -> None:
    selections = WizardSelections(
        root_path="",
        repo_url="https://github.com/org/repo.git",
        repo_path_wsl="",
        layout="grid",
        panes=2,
        cleanup="session",
        wsl_distribution="Ubuntu",
        tmux_auto_install=True,
        assignments={
            1: ("/home/demo/repo-a", "origin/main"),
            2: ("/home/demo/repo-b", "origin/release"),
        },
    )

    def home_resolver(**_: object) -> PurePosixPath:
        return PurePosixPath("/home/demo")

    loaded_repos: list[str] = []

    def branch_loader(**kwargs: object) -> list[str]:
        repo_path = str(kwargs["repo_path_wsl"])
        loaded_repos.append(repo_path)
        if repo_path.endswith("repo-a"):
            return ["origin/main"]
        if repo_path.endswith("repo-b"):
            return ["origin/release"]
        return []

    request = build_orchestration_request(
        selections,
        ["Ubuntu"],
        home_resolver=home_resolver,
        repo_sync=lambda **_: PurePosixPath("/home/demo/repo"),
        branch_loader=branch_loader,
    )
    assert [str(item.repo_path) for item in request.assignments] == ["/home/demo/repo-a", "/home/demo/repo-b"]
    assert loaded_repos == ["/home/demo/repo-a", "/home/demo/repo-b"]


def test_format_runtime_events_is_readable() -> None:
    panel = RuntimeOutputPanel()
    panel.record_started("discover", "basladi")
    panel.record_success("discover", "tamam")
    text = format_runtime_events(panel)
    assert "[started] discover: basladi" in text
    assert "[success] discover: tamam" in text


def test_tmux_shortcuts_lines_contains_attach_command() -> None:
    lines = tmux_shortcuts_lines("Ubuntu", "branchnexus")
    assert any("Kisayollar:" in item for item in lines)
    assert any("Ctrl+b" in item for item in lines)
    assert any("Mouse ile panel gecis" in item for item in lines)
    assert any("Ctrl + Mouse Wheel" in item for item in lines)
    assert any("Ctrl + '+' / Ctrl + '-'" in item for item in lines)
    assert any("wsl -d Ubuntu -- tmux attach-session -t branchnexus" in item for item in lines)


def test_build_terminal_launch_commands_prefers_windows_terminal() -> None:
    which = lambda name: "wt.exe" if name in {"wt.exe", "wt"} else None

    def command_builder(distribution: str, command: list[str]) -> list[str]:
        assert distribution == "Ubuntu"
        assert command == ["tmux", "attach-session", "-t", "branchnexus"]
        return ["wsl.exe", "-d", "Ubuntu", "--", *command]

    commands = build_terminal_launch_commands(
        "Ubuntu",
        "branchnexus",
        which=which,
        environ={},
        command_builder=command_builder,
    )
    assert commands[0][0] == [
        "wt.exe",
        "wsl.exe",
        "-d",
        "Ubuntu",
        "--",
        "tmux",
        "attach-session",
        "-t",
        "branchnexus",
    ]
    assert commands[0][1] == 0
    assert commands[1][0][:3] == ["wt.exe", "new-tab", "--title"]
    assert commands[-1][0] == ["wsl.exe", "-d", "Ubuntu", "--", "tmux", "attach-session", "-t", "branchnexus"]


def test_build_terminal_launch_commands_include_windowsapps_candidate() -> None:
    commands = build_terminal_launch_commands(
        "Ubuntu",
        "bnx",
        which=lambda _name: None,
        environ={"LOCALAPPDATA": r"C:\Users\demo\AppData\Local"},
        command_builder=lambda distribution, command: ["wsl.exe", "-d", distribution, "--", *command],
    )
    assert commands[0][0][0] == "wt.exe"
    assert commands[2][0][0].replace("/", "\\").endswith(r"Microsoft\WindowsApps\wt.exe")
    assert commands[-1][0] == ["wsl.exe", "-d", "Ubuntu", "--", "tmux", "attach-session", "-t", "bnx"]
    assert isinstance(commands[-1][1], int)


def test_build_runtime_open_commands_for_wsl() -> None:
    commands = build_runtime_open_commands(
        RuntimeKind.WSL,
        pane_count=4,
        wsl_distribution="Ubuntu",
        repo_branch_pairs=[
            ("https://github.com/org/repo.git", "main"),
            ("https://github.com/org/other.git", "origin/feature-x"),
        ],
        workspace_root_wsl="/work/repos",
        which=lambda _name: None,
        environ={"LOCALAPPDATA": r"C:\Users\demo\AppData\Local"},
    )
    assert commands[0][0][0] == "wsl.exe"
    assert commands[0][0][1:5] == ["-d", "Ubuntu", "--", "bash"]
    assert commands[0][0][5] == "-lc"
    assert "tmux set-environment -g BRANCHNEXUS_GH_TOKEN" in commands[0][0][6]
    assert "tmux kill-session -t branchnexus-runtime" in commands[0][0][6]
    assert "tmux new-session -d -s branchnexus-runtime" in commands[0][0][6]
    assert "tmux split-window -t branchnexus-runtime" in commands[0][0][6]
    assert "tmux bind-key -n WheelUpPane send-keys -M" in commands[0][0][6]
    assert "tmux bind-key -n WheelDownPane send-keys -M" in commands[0][0][6]
    assert "tmux set-hook -t branchnexus-runtime client-resized" in commands[0][0][6]
    assert "select-layout -t branchnexus-runtime:0 tiled" in commands[0][0][6]
    assert "PROMPT_DIRTRIM=1" in commands[0][0][6]
    assert "bash -lc '" in commands[0][0][6]
    assert "git clone https://github.com/org/repo.git" in commands[0][0][6]
    assert 'http.extraheader="Authorization: Bearer ${BRANCHNEXUS_GH_TOKEN}"' in commands[0][0][6]
    assert "git switch feature-x" in commands[0][0][6]
    assert commands[-1][0] == ["powershell.exe", "-NoExit", "-Command", "wsl -d Ubuntu"]


def test_build_runtime_wait_open_commands_for_wsl() -> None:
    commands = build_runtime_wait_open_commands(
        wsl_distribution="Ubuntu-20.04",
        session_name="branchnexus-runtime",
        progress_log_path="/home/demo/branchnexus-workspace/.bnx/runtime/open-progress.log",
    )
    assert commands[0][0][0] == "wsl.exe"
    assert commands[0][0][1:5] == ["-d", "Ubuntu-20.04", "--", "bash"]
    assert commands[0][0][5] == "-lc"
    assert "tmux has-session -t branchnexus-runtime" in commands[0][0][6]
    assert "tmux attach-session -t branchnexus-runtime" in commands[0][0][6]
    assert 'tail -n +1 -F "$progress_log" &' in commands[0][0][6]
    assert 'if [ -z "${progress_log:-}" ]; then progress_log=' in commands[0][0][6]
    assert "&;" not in commands[0][0][6]
    assert "Canli log dosyasi" in commands[0][0][6]
    assert "PROMPT_DIRTRIM=1" in commands[0][0][6]


def test_build_runtime_wait_open_commands_without_progress_log() -> None:
    commands = build_runtime_wait_open_commands(
        wsl_distribution="Ubuntu-20.04",
        session_name="branchnexus-runtime",
    )
    assert commands[0][0][0] == "wsl.exe"
    assert 'tail -n +1 -F "$progress_log" &' in commands[0][0][6]
    assert "progress_log=/tmp/branchnexus-open-progress.log" in commands[0][0][6]
    assert 'if [ -z "${progress_log:-}" ]; then progress_log=' in commands[0][0][6]
    assert "tmux attach-session -t branchnexus-runtime" in commands[0][0][6]


def test_build_runtime_open_commands_for_powershell() -> None:
    commands = build_runtime_open_commands(
        RuntimeKind.POWERSHELL,
        which=lambda _name: None,
        environ={},
    )
    assert commands[0][0][0] == "wt.exe"
    assert commands[0][0][1:] == ["powershell.exe", "-NoLogo", "-NoProfile"]
    assert commands[-1][0] == ["powershell.exe", "-NoLogo", "-NoProfile"]


def test_build_runtime_wsl_bootstrap_command_uses_home_workspace_for_non_wsl_root() -> None:
    bootstrap = build_runtime_wsl_bootstrap_command(
        pane_count=2,
        repo_branch_pairs=[("https://github.com/org/repo.git", "main")],
        workspace_root_wsl=r"C:\repos",
    )
    assert 'mkdir -p "$HOME/branchnexus-workspace/repo"' in bootstrap
    assert 'cd "$HOME/branchnexus-workspace/repo/pane-1"' in bootstrap
    assert "tmux set-option -t branchnexus-runtime mouse on" in bootstrap
    assert "tmux bind-key -n WheelUpPane send-keys -M" in bootstrap
    assert "tmux bind-key -n WheelDownPane send-keys -M" in bootstrap
    assert "tmux set-option -t branchnexus-runtime status-style" in bootstrap


def test_build_runtime_wsl_bootstrap_command_isolates_same_repo_per_pane() -> None:
    bootstrap = build_runtime_wsl_bootstrap_command(
        pane_count=2,
        repo_branch_pairs=[
            ("https://github.com/org/repo.git", "main"),
            ("https://github.com/org/repo.git", "feature-x"),
        ],
        workspace_root_wsl="/work/root",
    )
    assert '"/work/root/repo/pane-1"' in bootstrap
    assert '"/work/root/repo/pane-2"' in bootstrap


def test_build_runtime_wsl_attach_command_uses_prepared_paths() -> None:
    command = build_runtime_wsl_attach_command(
        pane_paths=[
            "/work/root/repo/pane-1-main",
            "/work/root/repo/pane-2-feature",
        ]
    )
    assert "tmux new-session -d -s branchnexus-runtime -c /work/root/repo/pane-1-main" in command
    assert "tmux split-window -t branchnexus-runtime -c /work/root/repo/pane-2-feature" in command
    assert "bash -i" in command
    assert "PROMPT_DIRTRIM=1" in command
    assert "[BranchNexus] cwd=" not in command
    assert "tmux set-option -t branchnexus-runtime mouse on" in command
    assert "tmux bind-key -n WheelUpPane send-keys -M" in command
    assert "tmux bind-key -n WheelDownPane send-keys -M" in command
    assert "tmux set-option -t branchnexus-runtime status-style" in command
    assert "tmux set-hook -t branchnexus-runtime client-resized" in command
    assert "select-layout -t branchnexus-runtime:0 tiled" in command


def test_build_runtime_wsl_attach_command_can_skip_attach() -> None:
    command = build_runtime_wsl_attach_command(
        pane_paths=["/work/root/repo/pane-1-main"],
        attach=False,
    )
    assert "tmux attach-session -t branchnexus-runtime" not in command
    assert "tmux new-session -d -s branchnexus-runtime -c /work/root/repo/pane-1-main" in command


def test_build_runtime_wsl_bootstrap_command_honors_horizontal_template() -> None:
    bootstrap = build_runtime_wsl_bootstrap_command(
        pane_count=3,
        repo_branch_pairs=[
            ("https://github.com/org/repo-a.git", "main"),
            ("https://github.com/org/repo-b.git", "main"),
            ("https://github.com/org/repo-c.git", "main"),
        ],
        workspace_root_wsl="/work/root",
        layout_rows=1,
        layout_cols=3,
    )
    assert "tmux select-layout -t branchnexus-runtime even-horizontal" in bootstrap
    assert "tmux set-hook -t branchnexus-runtime client-resized" in bootstrap
    assert "select-layout -t branchnexus-runtime:0 even-horizontal" in bootstrap


def test_build_runtime_wsl_attach_command_honors_vertical_template() -> None:
    command = build_runtime_wsl_attach_command(
        pane_paths=[
            "/work/root/repo/pane-1-main",
            "/work/root/repo/pane-2-main",
            "/work/root/repo/pane-3-main",
        ],
        layout_rows=3,
        layout_cols=1,
    )
    assert "tmux select-layout -t branchnexus-runtime even-vertical" in command
    assert "tmux set-hook -t branchnexus-runtime client-resized" in command
    assert "select-layout -t branchnexus-runtime:0 even-vertical" in command


def test_select_runtime_wsl_distribution_prefers_current_then_configured_then_first() -> None:
    available = ["Ubuntu-20.04", "Debian"]
    assert (
        select_runtime_wsl_distribution(available, configured="Debian", current="Ubuntu-20.04")
        == "Ubuntu-20.04"
    )
    assert select_runtime_wsl_distribution(available, configured="Debian", current="") == "Debian"
    assert select_runtime_wsl_distribution(available, configured="", current="") == "Ubuntu-20.04"


def test_select_runtime_wsl_distribution_returns_empty_when_unavailable() -> None:
    assert select_runtime_wsl_distribution([], configured="Ubuntu", current="Debian") == ""
