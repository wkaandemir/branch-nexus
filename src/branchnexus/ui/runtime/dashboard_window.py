"""Runtime dashboard window and launch."""

from __future__ import annotations

import logging as py_logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from branchnexus.config import AppConfig, save_config
from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.git.github_repositories import (
    GitHubRepository,
    list_github_repositories,
    list_github_repository_branches,
)
from branchnexus.runtime.wsl_discovery import list_distributions
from branchnexus.session import build_runtime_snapshot, parse_runtime_snapshot
from branchnexus.terminal import RuntimeKind, TerminalService
from branchnexus.tmux.bootstrap import ensure_tmux
from branchnexus.ui.screens.runtime_dashboard import RuntimeDashboardScreen
from branchnexus.ui.services.github_env import github_token_env
from branchnexus.ui.services.github_service import _github_repo_full_name_from_url
from branchnexus.ui.services.session_manager import _resolve_runtime_workspace_root_wsl
from branchnexus.ui.services.windows_terminal import _apply_windows_terminal_profile_font_size
from branchnexus.ui.state import AppState

from branchnexus.ui.runtime.runtime_progress import (
    _format_terminal_progress_line,
    append_wsl_progress_log as _append_wsl_progress_log,
    build_runtime_progress_log_path as _build_runtime_progress_log_path,
    init_wsl_progress_log as _init_wsl_progress_log,
)
from branchnexus.ui.runtime.runtime_tmux import (
    prepare_runtime_wsl_attach_session,
    prepare_runtime_wsl_failure_session,
    reset_runtime_wsl_session,
)
from branchnexus.ui.runtime.terminal_launch import open_runtime_terminal
from branchnexus.ui.runtime.wsl_preflight import (
    _resolve_wsl_target_path,
    _workspace_root_expression,
    prepare_wsl_runtime_pane_paths,
    select_runtime_wsl_distribution,
)

logger = py_logging.getLogger(__name__)
_DEFAULT_WSL_PROGRESS_LOG_PATH = "/tmp/branchnexus-open-progress.log"  # nosec B108

def launch_runtime_dashboard(
    *,
    config: AppConfig,
    state: AppState,
    config_path: str | Path | None = None,
    run_ui: bool = False,
) -> int:
    default_runtime = RuntimeKind.WSL
    if config.terminal_default_runtime != RuntimeKind.WSL.value:
        logger.info(
            "runtime-v2 forcing-default-runtime runtime=%s forced=%s",
            config.terminal_default_runtime,
            RuntimeKind.WSL.value,
        )
        config.terminal_default_runtime = RuntimeKind.WSL.value
        save_config(config, config_path)

    service = TerminalService(
        max_terminals=config.terminal_max_count,
        default_runtime=default_runtime,
    )
    dashboard = RuntimeDashboardScreen(
        service,
        template=config.default_panes,
        custom_terminal_count=config.default_panes,
        default_runtime=default_runtime,
    )

    restored = False
    if config.session_restore_enabled:
        snapshot = parse_runtime_snapshot(config.last_session)
        if snapshot is not None:
            snapshot_payload = snapshot.to_dict()
            terminals_payload = snapshot_payload.get("terminals", [])
            if isinstance(terminals_payload, list):
                for item in terminals_payload:
                    if isinstance(item, dict):
                        item["runtime"] = RuntimeKind.WSL.value
            restored = dashboard.restore_snapshot(snapshot_payload)

    if not restored:
        dashboard.bootstrap()

    panels = dashboard.list_panels()
    state.terminal_template = dashboard.template_count
    state.max_terminals = config.terminal_max_count
    state.terminal_default_runtime = default_runtime.value
    state.focused_terminal_id = dashboard.focused_terminal_id or (
        panels[0].terminal_id if panels else ""
    )

    def persist_snapshot() -> None:
        if not config.session_restore_enabled:
            return
        snapshot = build_runtime_snapshot(
            layout=config.default_layout,
            template_count=dashboard.template_count,
            terminals=service.list_instances(),
            focused_terminal_id=dashboard.focused_terminal_id,
        )
        config.last_session = snapshot.to_dict()
        save_config(config, config_path)

    persist_snapshot()
    if not run_ui:
        return int(ExitCode.SUCCESS)

    try:
        from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
        from PySide6.QtWidgets import (
            QApplication,
            QComboBox,
            QGridLayout,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSpinBox,
            QTableWidget,
            QTableWidgetItem,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as exc:
        raise BranchNexusError(
            "PySide6 kurulu degil; runtime dashboard acilamadi.",
            code=ExitCode.RUNTIME_ERROR,
            hint="`pip install PySide6` komutunu calistirip tekrar deneyin.",
        ) from exc

    class RepoLoadWorker(QObject):  # pragma: no cover
        succeeded = Signal(object, object)  # repositories, branches_by_repo
        failed = Signal(str)
        finished = Signal()

        def __init__(self, token: str) -> None:
            super().__init__()
            self.token = token

        @Slot()
        def run(self) -> None:
            try:
                repositories = list_github_repositories(self.token)
                branches_by_repo: dict[str, list[str]] = {}
                for repository in repositories:
                    try:
                        branches_by_repo[repository.full_name] = list_github_repository_branches(
                            self.token,
                            repository.full_name,
                        )
                    except BranchNexusError:
                        branches_by_repo[repository.full_name] = []
                self.succeeded.emit(repositories, branches_by_repo)
            except BranchNexusError as exc:
                self.failed.emit(str(exc))
            except Exception as exc:
                self.failed.emit(str(exc))
            finally:
                self.finished.emit()

    class BranchLoadWorker(QObject):  # pragma: no cover
        succeeded = Signal(str, str, object)  # repo_name, terminal_id, branches
        failed = Signal(str, str, str)  # repo_name, terminal_id, message
        finished = Signal()

        def __init__(self, token: str, repo_name: str, terminal_id: str) -> None:
            super().__init__()
            self.token = token
            self.repo_name = repo_name
            self.terminal_id = terminal_id

        @Slot()
        def run(self) -> None:
            try:
                branches = list_github_repository_branches(self.token, self.repo_name)
                self.succeeded.emit(self.repo_name, self.terminal_id, branches)
            except BranchNexusError as exc:
                self.failed.emit(self.repo_name, self.terminal_id, str(exc))
            except Exception as exc:
                self.failed.emit(self.repo_name, self.terminal_id, str(exc))
            finally:
                self.finished.emit()

    class OpenTerminalWorker(QObject):  # pragma: no cover
        succeeded = Signal(object)  # {"pane_count": int}
        progress = Signal(str, str)  # step, message
        failed = Signal(str, str)  # kind, message
        finished = Signal()

        def __init__(
            self,
            *,
            runtime: RuntimeKind,
            pane_count: int,
            layout_rows: int,
            layout_cols: int,
            wsl_distribution: str,
            wsl_pairs: list[tuple[str, str]],
            workspace_root_wsl: str,
            github_token: str,
            terminal_font_size: int,
        ) -> None:
            super().__init__()
            self.runtime = runtime
            self.pane_count = pane_count
            self.layout_rows = layout_rows
            self.layout_cols = layout_cols
            self.wsl_distribution = wsl_distribution
            self.wsl_pairs = wsl_pairs
            self.workspace_root_wsl = workspace_root_wsl
            self.github_token = github_token.strip()
            self.terminal_font_size = max(8, min(24, int(terminal_font_size)))

        @Slot()
        def run(self) -> None:
            pane_count = self.pane_count
            prepared_wsl_paths: list[str] = []
            launch_env = github_token_env(self.github_token) if self.github_token else None
            progress_log_path = ""
            terminal_progress_sink: Callable[[str], None] | None = None
            try:
                if self.runtime == RuntimeKind.WSL:
                    if not self.wsl_distribution.strip():
                        raise BranchNexusError(
                            "WSL dagitimi secilmedi.",
                            code=ExitCode.VALIDATION_ERROR,
                        )
                    workspace_root = _resolve_runtime_workspace_root_wsl(
                        self.wsl_distribution,
                        self.workspace_root_wsl,
                    )
                    progress_log_path = _build_runtime_progress_log_path(workspace_root)
                    if not progress_log_path:
                        progress_log_path = _DEFAULT_WSL_PROGRESS_LOG_PATH
                        logger.warning(
                            "runtime-open progress-log-path-empty using-default=%s",
                            progress_log_path,
                        )
                    _init_wsl_progress_log(
                        distribution=self.wsl_distribution,
                        log_path=progress_log_path,
                        env=launch_env,
                    )

                    def terminal_progress_sink(
                        line: str,
                        *,
                        _distribution: str = self.wsl_distribution,
                        _path: str = progress_log_path,
                        _env: dict[str, str] | None = launch_env,
                    ) -> None:
                        logger.info("runtime-open live %s", line)
                        _append_wsl_progress_log(
                            distribution=_distribution,
                            log_path=_path,
                            line=line,
                            env=_env,
                        )

                    terminal_progress_sink(
                        _format_terminal_progress_line(
                            "INFO",
                            "open-start",
                            (
                                f"workspace={workspace_root} runtime=wsl "
                                f"pane_count={self.pane_count}"
                            ),
                        )
                    )
                    self.progress.emit("open-preflight", "Runtime hazirlik adimlari baslatildi...")
                    self.progress.emit("tmux-bootstrap", "tmux kontrol ediliyor...")
                    ensure_tmux(
                        self.wsl_distribution,
                        auto_install=True,
                        runner=subprocess.run,
                    )
                    self.progress.emit("tmux-bootstrap", "tmux hazir.")
                    reset_runtime_wsl_session(
                        distribution=self.wsl_distribution,
                        env=launch_env,
                        verbose_sink=terminal_progress_sink,
                    )

                    def preflight_progress(step: str, message: str) -> None:
                        self.progress.emit(step, message)

                    prepared_wsl_paths = prepare_wsl_runtime_pane_paths(
                        distribution=self.wsl_distribution,
                        repo_branch_pairs=self.wsl_pairs,
                        workspace_root_wsl=workspace_root,
                        github_token=self.github_token,
                        progress=preflight_progress,
                        verbose_sink=terminal_progress_sink,
                    )
                    pane_count = max(1, len(prepared_wsl_paths))
                    font_applied, font_reason = _apply_windows_terminal_profile_font_size(
                        distribution=self.wsl_distribution,
                        font_size=self.terminal_font_size,
                    )
                    if font_applied:
                        self.progress.emit(
                            "terminal-font",
                            f"Terminal yazi boyutu uygulandi: {self.terminal_font_size}px",
                        )
                    else:
                        logger.info(
                            "runtime-open terminal-font-skip distribution=%s reason=%s",
                            self.wsl_distribution,
                            font_reason,
                        )
                    self.progress.emit("open-session", "WSL terminali aciliyor...")
                    opened = open_runtime_terminal(
                        RuntimeKind.WSL,
                        pane_count=pane_count,
                        wsl_distribution=self.wsl_distribution,
                        wsl_pane_paths=prepared_wsl_paths,
                        layout_rows=self.layout_rows,
                        layout_cols=self.layout_cols,
                        environ=launch_env,
                    )
                else:
                    opened = open_runtime_terminal(
                        self.runtime,
                        pane_count=pane_count,
                        wsl_distribution=self.wsl_distribution,
                        wsl_pane_paths=prepared_wsl_paths or None,
                        repo_branch_pairs=self.wsl_pairs,
                        workspace_root_wsl=self.workspace_root_wsl,
                        layout_rows=self.layout_rows,
                        layout_cols=self.layout_cols,
                        environ=launch_env,
                    )
            except BranchNexusError as exc:
                self.failed.emit("open-preflight-failed", str(exc))
                self.finished.emit()
                return
            except Exception as exc:
                logger.exception("runtime-open worker-unexpected-failure")
                self.failed.emit("open-preflight-failed", str(exc))
                self.finished.emit()
                return

            if not opened:
                self.failed.emit("open-failed", "Terminal acilamadi.")
                self.finished.emit()
                return

            self.succeeded.emit({"pane_count": pane_count})
            self.finished.emit()

    class RuntimeDashboardWindow(QMainWindow):  # pragma: no cover
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("BranchNexus Calisma Paneli")
            self.resize(950, 640)

            root = QWidget(self)
            self.setCentralWidget(root)
            layout = QVBoxLayout(root)
            self._repositories_by_name: dict[str, GitHubRepository] = {}
            self._branches_by_repo: dict[str, list[str]] = {}
            self._repo_combo_by_terminal: dict[str, QComboBox] = {}
            self._branch_combo_by_terminal: dict[str, QComboBox] = {}
            self._pending_repo_by_terminal: dict[str, str] = {}
            self._pending_branch_by_terminal: dict[str, str] = {}
            self._updating_table = False
            self._repo_load_thread: QThread | None = None
            self._repo_load_worker: RepoLoadWorker | None = None
            self._branch_load_thread: QThread | None = None
            self._branch_load_worker: BranchLoadWorker | None = None
            self._branch_load_terminal_id = ""
            self._branch_load_repo_name = ""
            self._open_thread: QThread | None = None
            self._open_worker: OpenTerminalWorker | None = None
            self._open_request_terminal_id = ""
            self._open_request_runtime = RuntimeKind.WSL.value
            self._open_request_pane_count = 1
            self._spinner_frames = ("|", "/", "-", "\\")
            self._load_spinner_index = 0
            self._open_spinner_index = 0
            self._available_wsl_distributions: list[str] = []
            self._hydrate_repository_cache_from_config()
            self._template_cards: dict[int, QPushButton] = {}
            self._template_dimensions: dict[int, tuple[int, int]] = {}
            self._terminal_font_size = 10

            controls = QGridLayout()
            controls.setContentsMargins(0, 0, 0, 0)
            controls.setHorizontalSpacing(4)
            controls.setVerticalSpacing(6)
            controls.setColumnMinimumWidth(0, 45)
            controls.setColumnStretch(1, 1)

            self.grid_rows_spin = QSpinBox()
            self.grid_rows_spin.setRange(1, 16)
            self.grid_rows_spin.setValue(2)
            self.grid_rows_spin.setFixedWidth(65)
            self.grid_rows_spin.setFixedHeight(28)
            self.grid_rows_spin.setProperty("grid_compact", True)
            self.grid_rows_spin.setToolTip("Satir sayisi")

            self.grid_cols_spin = QSpinBox()
            self.grid_cols_spin.setRange(1, 16)
            self.grid_cols_spin.setValue(2)
            self.grid_cols_spin.setFixedWidth(65)
            self.grid_cols_spin.setFixedHeight(28)
            self.grid_cols_spin.setProperty("grid_compact", True)
            self.grid_cols_spin.setToolTip("Sutun sayisi")

            self.font_size_spin = QSpinBox()
            self.font_size_spin.setRange(8, 24)
            self.font_size_spin.setValue(self._terminal_font_size)
            self.font_size_spin.setFixedWidth(65)
            self.font_size_spin.setFixedHeight(28)
            self.font_size_spin.setProperty("grid_compact", True)
            self.font_size_spin.setToolTip("Acilan split terminal yazisi (px)")

            self.grid_apply_btn = QPushButton("Uygula")
            self.grid_apply_btn.setProperty("secondary_btn", True)
            self.grid_apply_btn.setFixedWidth(80)
            self.grid_apply_btn.setFixedHeight(34)
            grid_controls = QWidget()
            grid_controls_row = QHBoxLayout(grid_controls)
            grid_controls_row.setContentsMargins(0, 0, 0, 0)
            grid_controls_row.setSpacing(4)
            grid_title_label = QLabel("â†”")
            grid_title_label.setProperty("grid_title_label", True)
            grid_controls_row.addWidget(grid_title_label)
            grid_controls_row.addSpacing(2)
            grid_controls_row.addWidget(self.grid_rows_spin)
            grid_mul_label = QLabel("x")
            grid_mul_label.setProperty("grid_separator", True)
            grid_controls_row.addWidget(grid_mul_label)
            grid_controls_row.addWidget(self.grid_cols_spin)
            grid_controls_row.addSpacing(4)
            font_title_label = QLabel("F")
            font_title_label.setProperty("grid_title_label", True)
            grid_controls_row.addWidget(font_title_label)
            grid_controls_row.addWidget(self.font_size_spin)
            grid_controls_row.addStretch(1)

            self.add_btn = QPushButton("Ekle")
            self.add_btn.setProperty("secondary_btn", True)
            self.remove_btn = QPushButton("Kaldir")
            self.remove_btn.setProperty("secondary_btn", True)
            self.open_btn = QPushButton("Baslat")
            self.open_btn.setProperty("action_btn", True)
            self.add_btn.setFixedWidth(80)
            self.remove_btn.setFixedWidth(80)
            self.open_btn.setFixedWidth(90)
            self.add_btn.setFixedHeight(34)
            self.remove_btn.setFixedHeight(34)
            self.open_btn.setFixedHeight(34)
            self.open_spinner = QLabel("")
            self.open_spinner.setMinimumWidth(24)
            self.open_spinner.setMinimumHeight(36)
            self.open_spinner.setStyleSheet("color: #5ec2f2;")
            terminal_actions = QWidget()
            terminal_actions_row = QHBoxLayout(terminal_actions)
            terminal_actions_row.setContentsMargins(0, 0, 0, 0)
            terminal_actions_row.setSpacing(6)
            terminal_actions_row.addWidget(self.add_btn)
            terminal_actions_row.addWidget(self.remove_btn)
            terminal_actions_row.addWidget(self.open_btn)
            terminal_actions_row.addWidget(self.open_spinner)
            terminal_actions_row.addStretch(0)
            terminal_actions_row.addWidget(grid_controls, 0, Qt.AlignmentFlag.AlignLeft)
            controls.addWidget(QLabel("Term"), 2, 0)
            controls.addWidget(terminal_actions, 2, 1)
            controls.addWidget(self.grid_apply_btn, 2, 2, Qt.AlignmentFlag.AlignLeft)
            self.open_spinner_timer = QTimer(self)
            self.open_spinner_timer.setInterval(90)
            self.open_spinner_timer.timeout.connect(self._tick_open_spinner)

            controls.addWidget(QLabel("Token"), 0, 0)
            self.github_token_edit = QLineEdit(config.github_token)
            self.github_token_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self.github_token_edit.setPlaceholderText("ghp_xxx")
            self.github_token_edit.setFixedHeight(34)
            controls.addWidget(self.github_token_edit, 0, 1)
            self.load_repos_btn = QPushButton("Getir")
            self.load_repos_btn.setProperty("secondary_btn", True)
            self.load_repos_btn.setFixedWidth(75)
            self.load_repos_btn.setFixedHeight(34)
            self.load_spinner = QLabel("")
            self.load_spinner.setMinimumWidth(24)
            self.load_spinner.setStyleSheet("color: #5ec2f2;")
            repo_actions = QWidget()
            repo_actions_row = QHBoxLayout(repo_actions)
            repo_actions_row.setContentsMargins(0, 0, 0, 0)
            repo_actions_row.setSpacing(6)
            repo_actions_row.addWidget(self.load_repos_btn)
            repo_actions_row.addWidget(self.load_spinner)
            repo_actions_row.addStretch(1)
            controls.addWidget(repo_actions, 0, 2, Qt.AlignmentFlag.AlignLeft)
            self.load_spinner_timer = QTimer(self)
            self.load_spinner_timer.setInterval(90)
            self.load_spinner_timer.timeout.connect(self._tick_spinner)

            controls.addWidget(QLabel("WSL"), 1, 0)
            self.wsl_distribution_combo = QComboBox()
            self.wsl_distribution_combo.setMinimumContentsLength(20)
            self.wsl_distribution_combo.setFixedHeight(34)
            controls.addWidget(self.wsl_distribution_combo, 1, 1)
            self.reload_wsl_btn = QPushButton("Yenile")
            self.reload_wsl_btn.setProperty("secondary_btn", True)
            self.reload_wsl_btn.setFixedWidth(75)
            self.reload_wsl_btn.setFixedHeight(34)
            controls.addWidget(self.reload_wsl_btn, 1, 2, Qt.AlignmentFlag.AlignLeft)

            layout.addLayout(controls)

            cards_layout = QGridLayout()
            cards_layout.setContentsMargins(0, 4, 0, 10)
            cards_layout.setHorizontalSpacing(10)
            cards_layout.setVerticalSpacing(0)
            template_specs = [
                (2, 1, 2),
                (3, 1, 3),
                (4, 2, 2),
                (6, 2, 3),
                (8, 2, 4),
                (9, 3, 3),
                (12, 3, 4),
                (16, 4, 4),
            ]
            for index, (count, preview_rows, preview_cols) in enumerate(template_specs):
                preview = self._template_preview(preview_rows, preview_cols)
                card = QPushButton(f"{count}\n{preview}")
                card.setCheckable(True)
                card.setProperty("template_card", True)
                card.setCursor(Qt.CursorShape.PointingHandCursor)
                card.setFixedSize(94, 94)
                card.setToolTip(f"{count} terminal")
                row = 0
                col = index
                cards_layout.addWidget(card, row, col)
                card.clicked.connect(
                    lambda _checked, value=count: self._set_template_from_card(value)
                )
                self._template_cards[count] = card
                self._template_dimensions[count] = (preview_rows, preview_cols)
            cards_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            layout.addLayout(cards_layout)

            self.table = QTableWidget(0, 4)
            self.table.setHorizontalHeaderLabels(["Terminal", "Baslik", "Depo", "Dal"])
            self._terminal_row_height = 36
            self._terminal_cell_height = 34
            self.table.verticalHeader().setVisible(False)
            self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            self.table.verticalHeader().setDefaultSectionSize(self._terminal_row_height)
            self.table.verticalHeader().setMinimumSectionSize(self._terminal_row_height)
            self.table.verticalHeader().setMaximumSectionSize(self._terminal_row_height)
            self.table.horizontalHeader().setStretchLastSection(False)
            self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
            self._apply_table_column_widths()
            layout.addWidget(self.table)

            self.status = QLabel("")
            layout.addWidget(self.status)

            self.add_btn.clicked.connect(self._add_terminal)
            self.remove_btn.clicked.connect(self._remove_terminal)
            self.open_btn.clicked.connect(self._open_terminal)
            self.grid_apply_btn.clicked.connect(self._apply_grid_template)
            self.load_repos_btn.clicked.connect(self._load_repositories)
            self.reload_wsl_btn.clicked.connect(self._load_wsl_distributions)
            self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
            self.wsl_distribution_combo.currentTextChanged.connect(
                self._on_wsl_distribution_changed
            )
            self.table.itemSelectionChanged.connect(self._focus_selected)
            self._apply_visual_style()

            self._load_wsl_distributions(initial=True)
            self._sync_grid_inputs_from_count(dashboard.template_count)
            self._select_template_card(dashboard.template_count)
            self._refresh()
            if self._repositories_by_name:
                self._set_status(
                    f"{len(self._repositories_by_name)} kayitli repo otomatik yuklendi."
                )
            elif self.github_token_edit.text().strip():
                QTimer.singleShot(0, self._load_repositories)

        def _set_status(self, message: str, *, error: bool = False) -> None:
            self.status.setText(message)
            self.status.setStyleSheet("color: #b00020;" if error else "")

        def _hydrate_repository_cache_from_config(self) -> None:
            repositories: dict[str, GitHubRepository] = {}
            for item in config.github_repositories_cache:
                if not isinstance(item, dict):
                    continue
                full_name_raw = item.get("full_name")
                clone_url_raw = item.get("clone_url")
                if not isinstance(full_name_raw, str) or not isinstance(clone_url_raw, str):
                    continue
                full_name = full_name_raw.strip()
                clone_url = clone_url_raw.strip()
                if not full_name or not clone_url:
                    continue
                repositories[full_name] = GitHubRepository(full_name=full_name, clone_url=clone_url)
            self._repositories_by_name = repositories

            branches_by_repo: dict[str, list[str]] = {}
            for repo_name, branches in config.github_branches_cache.items():
                if not isinstance(repo_name, str) or not isinstance(branches, list):
                    continue
                key = repo_name.strip()
                if not key:
                    continue
                normalized_branches = [
                    branch.strip()
                    for branch in branches
                    if isinstance(branch, str) and branch.strip()
                ]
                branches_by_repo[key] = normalized_branches
            self._branches_by_repo = branches_by_repo

        def _persist_repository_cache(self) -> None:
            config.github_token = self.github_token_edit.text().strip()
            config.github_repositories_cache = [
                {"full_name": repository.full_name, "clone_url": repository.clone_url}
                for repository in sorted(
                    self._repositories_by_name.values(), key=lambda item: item.full_name.lower()
                )
            ]
            config.github_branches_cache = {
                repo_name: [
                    branch for branch in branches if isinstance(branch, str) and branch.strip()
                ]
                for repo_name, branches in sorted(self._branches_by_repo.items())
                if isinstance(repo_name, str) and repo_name.strip()
            }
            save_config(config, config_path)

        def _load_wsl_distributions(self, *, initial: bool = False) -> None:
            previous = self.wsl_distribution_combo.currentText().strip()
            configured = config.wsl_distribution.strip()
            try:
                distributions = list_distributions()
            except BranchNexusError as exc:
                self._available_wsl_distributions = []
                self.wsl_distribution_combo.blockSignals(True)
                self.wsl_distribution_combo.clear()
                self.wsl_distribution_combo.blockSignals(False)
                if not initial:
                    self._set_status(str(exc), error=True)
                logger.warning("runtime-open wsl-discovery-failed error=%s", exc.message)
                return

            self._available_wsl_distributions = distributions
            selected = select_runtime_wsl_distribution(
                distributions,
                configured=configured,
                current=previous,
            )

            self.wsl_distribution_combo.blockSignals(True)
            self.wsl_distribution_combo.clear()
            self.wsl_distribution_combo.addItems(distributions)
            if selected:
                self.wsl_distribution_combo.setCurrentText(selected)
            self.wsl_distribution_combo.blockSignals(False)

            if selected and config.wsl_distribution != selected:
                config.wsl_distribution = selected
                save_config(config, config_path)
            logger.info(
                "runtime-open wsl-discovery-success count=%s selected=%s",
                len(distributions),
                selected or "-",
            )

        def _on_wsl_distribution_changed(self, value: str) -> None:
            selected = value.strip()
            if not selected:
                return
            if selected == config.wsl_distribution:
                return
            config.wsl_distribution = selected
            save_config(config, config_path)
            logger.info("runtime-open wsl-selected distribution=%s", selected)
            self._set_status(f"WSL secildi: {selected}")

        def _selected_wsl_distribution(self) -> str:
            selected = self.wsl_distribution_combo.currentText().strip()
            if selected:
                return selected
            return config.wsl_distribution.strip()

        def _apply_table_column_widths(self) -> None:
            self.table.setColumnWidth(0, 100)  # Terminal
            self.table.setColumnWidth(1, 210)  # Baslik
            self.table.setColumnWidth(2, 460)  # Depo
            self.table.setColumnWidth(3, 240)  # Dal

        def _on_font_size_changed(self, value: int) -> None:
            self._terminal_font_size = max(8, min(24, int(value)))
            self._set_status(
                f"Terminal yazi boyutu ayarlandi: {self._terminal_font_size}px "
                "(bir sonraki Ac isleminde uygulanir)"
            )

        def _tick_spinner(self) -> None:
            frame = self._spinner_frames[self._load_spinner_index % len(self._spinner_frames)]
            self._load_spinner_index += 1
            self.load_spinner.setText(frame)

        def _tick_open_spinner(self) -> None:
            frame = self._spinner_frames[self._open_spinner_index % len(self._spinner_frames)]
            self._open_spinner_index += 1
            self.open_spinner.setText(frame)

        def _start_repo_loading_indicator(self) -> None:
            self._load_spinner_index = 0
            self.load_spinner.setText(self._spinner_frames[0])
            self.load_spinner_timer.start()
            self.load_repos_btn.setEnabled(False)

        def _stop_repo_loading_indicator(self) -> None:
            self.load_spinner_timer.stop()
            self.load_spinner.setText("")
            self.load_repos_btn.setEnabled(True)

        def _start_open_loading_indicator(self) -> None:
            self._open_spinner_index = 0
            self.open_spinner.setText(self._spinner_frames[0])
            self.open_spinner_timer.start()
            self.open_btn.setEnabled(False)
            self.add_btn.setEnabled(False)
            self.remove_btn.setEnabled(False)
            self.grid_apply_btn.setEnabled(False)
            self.grid_rows_spin.setEnabled(False)
            self.grid_cols_spin.setEnabled(False)
            self.font_size_spin.setEnabled(False)
            for card in self._template_cards.values():
                card.setEnabled(False)
            self.table.setEnabled(False)

        def _stop_open_loading_indicator(self) -> None:
            self.open_spinner_timer.stop()
            self.open_spinner.setText("")
            self.open_btn.setEnabled(True)
            self.add_btn.setEnabled(True)
            self.remove_btn.setEnabled(True)
            self.grid_apply_btn.setEnabled(True)
            self.grid_rows_spin.setEnabled(True)
            self.grid_cols_spin.setEnabled(True)
            self.font_size_spin.setEnabled(True)
            for card in self._template_cards.values():
                card.setEnabled(True)
            self.table.setEnabled(True)

        def _selected_terminal_id(self) -> str:
            indexes = self.table.selectionModel().selectedRows()
            if not indexes:
                return ""
            row = indexes[0].row()
            item = self.table.item(row, 0)
            if item is None:
                return ""
            return item.text().strip()

        def _focus_selected(self) -> None:
            if self._updating_table:
                return
            terminal_id = self._selected_terminal_id()
            if not terminal_id:
                return
            try:
                dashboard.focus_terminal(terminal_id)
            except BranchNexusError:
                return
            self._refresh()

        def _set_template_from_card(self, count: int) -> None:
            try:
                dashboard.set_template(str(count))
            except BranchNexusError as exc:
                self._set_status(str(exc), error=True)
                return
            self._sync_grid_inputs_from_count(count)
            self._select_template_card(dashboard.template_count)
            self._set_status(f"Sablon uygulandi: {dashboard.template_count} terminal")
            self._refresh()

        def _apply_grid_template(self) -> None:
            rows = self.grid_rows_spin.value()
            cols = self.grid_cols_spin.value()
            requested = rows * cols
            try:
                dashboard.set_template(str(requested))
            except BranchNexusError:
                self._set_status(
                    "Satir x sutun sonucu 2 ile 16 arasinda olmali.",
                    error=True,
                )
                return
            self._select_template_card(dashboard.template_count)
            self._set_status(f"{rows}x{cols} ile {dashboard.template_count} terminal olusturuldu.")
            self._refresh()

        def _sync_grid_inputs_from_count(self, count: int) -> None:
            dimensions = self._template_dimensions.get(count)
            if dimensions is None:
                dimensions = (1, count)
            rows, cols = dimensions
            self.grid_rows_spin.blockSignals(True)
            self.grid_cols_spin.blockSignals(True)
            self.grid_rows_spin.setValue(rows)
            self.grid_cols_spin.setValue(cols)
            self.grid_rows_spin.blockSignals(False)
            self.grid_cols_spin.blockSignals(False)

        def _add_terminal(self) -> None:
            try:
                dashboard.add_terminal(runtime=RuntimeKind.WSL)
            except BranchNexusError as exc:
                self._set_status(str(exc), error=True)
                return
            self._set_status("Terminal eklendi.")
            self._refresh()

        def _load_repositories(self) -> None:
            if self._repo_load_thread is not None:
                self._set_status("Repo listesi yukleniyor, lutfen bekleyin.")
                return
            token = self.github_token_edit.text().strip()
            if not token:
                self._set_status("GitHub token girilmedi.", error=True)
                return
            self._start_repo_loading_indicator()
            self._set_status("Repo listesi yukleniyor...")

            thread = QThread(self)
            worker = RepoLoadWorker(token)
            worker.moveToThread(thread)

            thread.started.connect(worker.run)
            worker.succeeded.connect(self._on_repo_load_success)
            worker.failed.connect(self._on_repo_load_failed)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._on_repo_load_done)

            self._repo_load_thread = thread
            self._repo_load_worker = worker
            thread.start()

        def _on_repo_load_success(self, repositories: object, branches_by_repo: object) -> None:
            if not isinstance(repositories, list):
                self._set_status("Repo listesi beklenmeyen formatta.", error=True)
                return
            if not isinstance(branches_by_repo, dict):
                self._set_status("Branch listesi beklenmeyen formatta.", error=True)
                return
            self._repositories_by_name = {
                item.full_name: item for item in repositories if isinstance(item, GitHubRepository)
            }
            self._branches_by_repo = {
                str(name): [
                    branch for branch in values if isinstance(branch, str) and branch.strip()
                ]
                if isinstance(values, list)
                else []
                for name, values in branches_by_repo.items()
            }
            self._persist_repository_cache()
            self._refresh()
            self._set_status(f"{len(self._repositories_by_name)} repo yuklendi.")

        def _on_repo_load_failed(self, message: str) -> None:
            self._set_status(message or "Repo listesi yuklenemedi.", error=True)

        def _on_repo_load_done(self) -> None:
            self._stop_repo_loading_indicator()
            self._repo_load_worker = None
            self._repo_load_thread = None

        def _load_branches_for_repo(self, repo_full_name: str) -> list[str]:
            repo_name = repo_full_name.strip()
            if not repo_name:
                return []
            return self._branches_by_repo.get(repo_name, [])

        def _load_branches_async(self, *, terminal_id: str, repo_name: str) -> None:
            if self._branch_load_thread is not None:
                self._set_status("Branch listesi yukleniyor, lutfen bekleyin.")
                return

            token = self.github_token_edit.text().strip()
            if not token:
                self._set_status("Branch yuklemek icin GitHub token girin.", error=True)
                return

            thread = QThread(self)
            worker = BranchLoadWorker(token, repo_name, terminal_id)
            worker.moveToThread(thread)

            thread.started.connect(worker.run)
            worker.succeeded.connect(self._on_branch_load_success)
            worker.failed.connect(self._on_branch_load_failed)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._on_branch_load_done)

            self._branch_load_thread = thread
            self._branch_load_worker = worker
            self._branch_load_terminal_id = terminal_id
            self._branch_load_repo_name = repo_name
            self._set_status(f"{repo_name} icin branch listesi yukleniyor...")
            thread.start()

        def _on_branch_load_success(
            self, repo_name: str, terminal_id: str, branches_payload: object
        ) -> None:
            if not isinstance(branches_payload, list):
                self._set_status(f"{repo_name} branch listesi beklenmeyen formatta.", error=True)
                return

            branches = [item for item in branches_payload if isinstance(item, str) and item.strip()]
            self._branches_by_repo[repo_name] = branches
            self._persist_repository_cache()
            if terminal_id:
                self._pending_branch_by_terminal[terminal_id] = branches[0] if branches else ""
            self._refresh()
            if terminal_id and branches:
                self._apply_auto_switch(terminal_id)
            self._set_status(f"{repo_name} icin {len(branches)} branch yuklendi.")

        def _on_branch_load_failed(self, repo_name: str, _terminal_id: str, message: str) -> None:
            self._set_status(message or f"{repo_name} branch listesi yuklenemedi.", error=True)

        def _on_branch_load_done(self) -> None:
            self._branch_load_worker = None
            self._branch_load_thread = None
            self._branch_load_terminal_id = ""
            self._branch_load_repo_name = ""

        def _remove_terminal(self) -> None:
            terminal_id = self._selected_terminal_id()
            if not terminal_id:
                self._set_status("Silinecek terminal secilmedi.", error=True)
                return

            dialog = QMessageBox(self)
            dialog.setWindowTitle("Remove Terminal")
            dialog.setText(f"{terminal_id} silinsin mi?")
            preserve_btn = dialog.addButton("Koruyarak Sil", QMessageBox.ButtonRole.ActionRole)
            clean_btn = dialog.addButton("Temizleyerek Sil", QMessageBox.ButtonRole.DestructiveRole)
            dialog.addButton("Vazgec", QMessageBox.ButtonRole.RejectRole)
            dialog.exec()
            clicked = dialog.clickedButton()
            if clicked not in {preserve_btn, clean_btn}:
                return

            cleanup = "clean" if clicked is clean_btn else "preserve"
            self._remove_terminal_by_id(terminal_id, cleanup=cleanup, announce=True)

        def _remove_terminal_by_id(
            self, terminal_id: str, *, cleanup: str = "preserve", announce: bool = True
        ) -> None:
            try:
                dashboard.remove_terminal(terminal_id, cleanup=cleanup)
            except BranchNexusError as exc:
                self._set_status(str(exc), error=True)
                return
            self._pending_repo_by_terminal.pop(terminal_id, None)
            self._pending_branch_by_terminal.pop(terminal_id, None)
            if announce:
                self._set_status(f"{terminal_id} kaldirildi ({cleanup}).")
            self._refresh()

        def _remove_terminal_inline(self, terminal_id: str) -> None:
            self._remove_terminal_by_id(terminal_id, cleanup="preserve", announce=True)

        def _open_terminal(self) -> None:
            if self._open_thread is not None:
                self._set_status("Open islemi devam ediyor, lutfen bekleyin.")
                return

            terminal_id = self._selected_terminal_id()
            if not terminal_id:
                self._set_status("Acilacak terminal secilmedi.", error=True)
                return

            instance = None
            for item in service.list_instances():
                if item.spec.terminal_id == terminal_id:
                    instance = item
                    break
            if instance is None:
                self._set_status("Terminal bulunamadi.", error=True)
                return

            if instance.spec.runtime != RuntimeKind.WSL:
                self._set_status("Bu surum yalnizca WSL runtime destekler.", error=True)
                return

            def resolve_terminal_context(
                spec_terminal_id: str, spec_repo_path: str, spec_branch: str
            ) -> tuple[str, str]:
                repo_name = self._pending_repo_by_terminal.get(spec_terminal_id, "").strip()
                branch_name = self._pending_branch_by_terminal.get(spec_terminal_id, "").strip()

                repo_combo = self._repo_combo_by_terminal.get(spec_terminal_id)
                if repo_combo is not None:
                    selected_repo = repo_combo.currentText().strip()
                    if selected_repo:
                        repo_name = selected_repo

                branch_combo = self._branch_combo_by_terminal.get(spec_terminal_id)
                if branch_combo is not None:
                    selected_branch = branch_combo.currentText().strip()
                    if selected_branch:
                        branch_name = selected_branch

                resolved_repo = spec_repo_path.strip()
                if repo_name:
                    selected_repo = self._repositories_by_name.get(repo_name)
                    if selected_repo is not None:
                        resolved_repo = selected_repo.clone_url
                    elif (
                        repo_name.startswith("/")
                        or "://" in repo_name
                        or repo_name.startswith("git@")
                    ):
                        resolved_repo = repo_name

                resolved_branch = branch_name or spec_branch.strip()
                return resolved_repo, resolved_branch

            wsl_pairs: list[tuple[str, str]] = []
            for item in service.list_instances():
                if item.spec.runtime != RuntimeKind.WSL:
                    continue
                resolved_repo, resolved_branch = resolve_terminal_context(
                    item.spec.terminal_id,
                    item.spec.repo_path,
                    item.spec.branch,
                )
                wsl_pairs.append((resolved_repo, resolved_branch))
            wsl_pairs = [
                (repo_path, branch)
                for repo_path, branch in wsl_pairs
                if repo_path.strip() and branch.strip()
            ]
            selected_wsl_distribution = self._selected_wsl_distribution()
            if not selected_wsl_distribution:
                self._set_status("WSL dagitimi secilmedi.", error=True)
                return
            resolved_workspace_root = _resolve_runtime_workspace_root_wsl(
                selected_wsl_distribution,
                config.default_root,
            )
            workspace_root = _workspace_root_expression(resolved_workspace_root)
            for pane_index, (repo_path, branch) in enumerate(wsl_pairs):
                logger.info(
                    "runtime-open resolved-pane pane=%s repo=%s branch=%s target=%s",
                    pane_index + 1,
                    repo_path,
                    branch,
                    _resolve_wsl_target_path(
                        repo_path,
                        workspace_root=workspace_root,
                        pane_index=pane_index,
                    ),
                )
            if not wsl_pairs:
                service.record_event(
                    terminal_id,
                    "open-skip",
                    "Open skipped: no repo/branch selections for WSL panes.",
                )
                logger.warning(
                    "Open skipped terminal=%s runtime=%s reason=no-wsl-selections",
                    terminal_id,
                    instance.spec.runtime.value,
                )
                self._set_status(
                    "Open icin once en az bir WSL terminalinde repo ve branch secin.",
                    error=True,
                )
                return

            pane_count = max(1, len(wsl_pairs))
            layout_rows = self.grid_rows_spin.value()
            layout_cols = self.grid_cols_spin.value()
            token_value = self.github_token_edit.text().strip()
            has_github_repo = any(
                _github_repo_full_name_from_url(repo_path) for repo_path, _branch in wsl_pairs
            )
            if has_github_repo and not token_value:
                self._set_status(
                    (
                        "GitHub depolari icin GitHub Anahtari gerekli. "
                        "Token girin; baglanti uygulama tarafindan otomatik kurulur."
                    ),
                    error=True,
                )
                return
            summary = ", ".join(f"{repo}@{branch}" for repo, branch in wsl_pairs)
            logger.info(
                "Open request terminal=%s runtime=%s panes=%s layout=%sx%s distro=%s selections=[%s]",
                terminal_id,
                instance.spec.runtime.value,
                pane_count,
                layout_rows,
                layout_cols,
                selected_wsl_distribution,
                summary,
            )
            service.record_event(
                terminal_id,
                "open-start",
                f"Opening {instance.spec.runtime.value} terminal pane_count={pane_count}.",
            )
            self._open_request_terminal_id = terminal_id
            self._open_request_runtime = instance.spec.runtime.value
            self._open_request_pane_count = pane_count
            self._start_open_loading_indicator()
            self._set_status("Terminal aciliyor, hazirlik adimlari baslatiliyor...")

            thread = QThread(self)
            worker = OpenTerminalWorker(
                runtime=instance.spec.runtime,
                pane_count=pane_count,
                layout_rows=layout_rows,
                layout_cols=layout_cols,
                wsl_distribution=selected_wsl_distribution,
                wsl_pairs=wsl_pairs,
                workspace_root_wsl=config.default_root,
                github_token=token_value,
                terminal_font_size=self._terminal_font_size,
            )
            worker.moveToThread(thread)

            thread.started.connect(worker.run)
            worker.succeeded.connect(self._on_open_success)
            worker.progress.connect(self._on_open_progress)
            worker.failed.connect(self._on_open_failed)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(self._on_open_done)

            self._open_worker = worker
            self._open_thread = thread
            thread.start()

        def _on_open_success(self, payload: object) -> None:
            pane_count = self._open_request_pane_count
            if isinstance(payload, dict):
                candidate = payload.get("pane_count")
                if isinstance(candidate, int) and candidate > 0:
                    pane_count = candidate

            terminal_id = self._open_request_terminal_id
            runtime = self._open_request_runtime
            service.record_event(
                terminal_id,
                "open-success",
                f"External {runtime} terminal launched.",
            )
            logger.info(
                "Open success terminal=%s runtime=%s panes=%s",
                terminal_id,
                runtime,
                pane_count,
            )
            self._set_status(f"{terminal_id} icin {runtime} terminali acildi.")
            self._refresh()

        def _on_open_progress(self, step: str, message: str) -> None:
            terminal_id = self._open_request_terminal_id
            event_step = step.strip() or "open-progress"
            if terminal_id:
                service.record_event(terminal_id, event_step, message)
            self._set_status(message)

        def _on_open_failed(self, kind: str, message: str) -> None:
            terminal_id = self._open_request_terminal_id
            runtime = self._open_request_runtime
            pane_count = self._open_request_pane_count
            if kind == "open-preflight-failed":
                service.record_event(
                    terminal_id,
                    "open-preflight-failed",
                    message,
                )
                logger.error(
                    "runtime-open preflight failed terminal=%s runtime=%s error=%s",
                    terminal_id,
                    runtime,
                    message,
                )
                self._set_status(message, error=True)
                self._refresh()
                return

            service.record_event(
                terminal_id,
                "open-failed",
                f"External {runtime} terminal launch failed.",
            )
            logger.error(
                "Open failed terminal=%s runtime=%s panes=%s",
                terminal_id,
                runtime,
                pane_count,
            )
            self._set_status(f"{terminal_id} icin terminal acilamadi.", error=True)
            self._refresh()

        def _on_open_done(self) -> None:
            self._stop_open_loading_indicator()
            self._open_worker = None
            self._open_thread = None

        def _on_row_repo_changed(self, terminal_id: str) -> None:
            repo_combo = self._repo_combo_by_terminal.get(terminal_id)
            branch_combo = self._branch_combo_by_terminal.get(terminal_id)
            if repo_combo is None or branch_combo is None:
                return
            self._select_row_for_terminal(terminal_id)

            repo_name = repo_combo.currentText().strip()
            self._pending_repo_by_terminal[terminal_id] = repo_name
            self._pending_branch_by_terminal[terminal_id] = ""
            branch_combo.clear()
            if not repo_name:
                return
            branches = self._load_branches_for_repo(repo_name)
            if not branches:
                self._load_branches_async(terminal_id=terminal_id, repo_name=repo_name)
                return

            branch_combo.addItems(branches)
            if branches:
                self._pending_branch_by_terminal[terminal_id] = branches[0]
                self._set_status(f"{repo_name} icin {len(branches)} branch yuklendi.")
                self._apply_auto_switch(terminal_id)

        def _on_row_branch_changed(self, terminal_id: str) -> None:
            branch_combo = self._branch_combo_by_terminal.get(terminal_id)
            if branch_combo is None:
                return
            self._select_row_for_terminal(terminal_id)
            self._pending_branch_by_terminal[terminal_id] = branch_combo.currentText().strip()
            self._apply_auto_switch(terminal_id)

        def _select_row_for_terminal(self, terminal_id: str) -> None:
            if self._updating_table:
                return
            for row in range(self.table.rowCount()):
                item = self.table.item(row, 0)
                if item is None:
                    continue
                if item.text().strip() != terminal_id:
                    continue
                self.table.selectRow(row)
                with suppress(BranchNexusError):
                    dashboard.focus_terminal(terminal_id)
                break

        def _apply_auto_switch(self, terminal_id: str) -> None:
            repo_combo = self._repo_combo_by_terminal.get(terminal_id)
            branch_combo = self._branch_combo_by_terminal.get(terminal_id)
            if repo_combo is None or branch_combo is None:
                return
            repo_name = repo_combo.currentText().strip()
            branch = branch_combo.currentText().strip()
            if not repo_name or not branch:
                return
            repo = self._repositories_by_name.get(repo_name)
            if repo is None:
                self._set_status("Depo bilgisi bulunamadi. Repo listesini yenileyin.", error=True)
                return

            instance = next(
                (item for item in service.list_instances() if item.spec.terminal_id == terminal_id),
                None,
            )
            if instance is None:
                self._set_status("Terminal bulunamadi.", error=True)
                return
            if instance.spec.repo_path == repo.clone_url and instance.spec.branch == branch:
                return

            try:
                dashboard.change_repo_branch(
                    terminal_id,
                    repo_path=repo.clone_url,
                    branch=branch,
                )
            except BranchNexusError as exc:
                self._set_status(str(exc), error=True)
                return
            self._pending_repo_by_terminal[terminal_id] = repo_name
            self._pending_branch_by_terminal[terminal_id] = branch
            self._set_status(f"{terminal_id} baglami guncellendi: {repo_name}:{branch}")
            self._refresh()

        def _refresh(self) -> None:
            self._updating_table = True
            try:
                panels_local = dashboard.list_panels()
                self.table.setRowCount(0)
                self._repo_combo_by_terminal.clear()
                self._branch_combo_by_terminal.clear()
                self._apply_table_column_widths()

                repo_names = sorted(self._repositories_by_name.keys(), key=str.lower)
                focus_row = -1

                for row, panel in enumerate(panels_local):
                    self.table.insertRow(row)
                    self.table.setRowHeight(row, self._terminal_row_height)
                    if panel.focused:
                        focus_row = row

                    terminal_item = QTableWidgetItem(panel.terminal_id)
                    self.table.setItem(row, 0, terminal_item)

                    title_widget = QWidget()
                    title_widget.setFixedHeight(self._terminal_cell_height)
                    title_layout = QHBoxLayout(title_widget)
                    title_layout.setContentsMargins(6, 1, 6, 1)
                    title_layout.setSpacing(6)
                    title_label = QLabel(panel.title)
                    title_label.setProperty("row_title_label", True)
                    remove_btn = QPushButton("Ã—")
                    remove_btn.setProperty("danger_btn", True)
                    remove_btn.setToolTip(f"{panel.terminal_id} terminalini kaldir")
                    remove_btn.setFixedSize(28, 28)
                    remove_btn.clicked.connect(
                        lambda _checked=False, terminal_id=panel.terminal_id: (
                            self._remove_terminal_inline(terminal_id)
                        )
                    )
                    title_layout.addWidget(title_label, 1)
                    title_layout.addWidget(remove_btn, 0, Qt.AlignmentFlag.AlignRight)
                    self.table.setCellWidget(row, 1, title_widget)

                    repo_combo = QComboBox()
                    repo_combo.setFixedHeight(self._terminal_cell_height)
                    repo_combo.setProperty("table_row_combo", True)
                    repo_combo.setMinimumContentsLength(20)
                    repo_combo.addItem("")
                    for repo_name in repo_names:
                        repo_combo.addItem(repo_name)

                    selected_repo_name = self._pending_repo_by_terminal.get(panel.terminal_id, "")
                    if not selected_repo_name and panel.repo_path:
                        for repo_name, repo in self._repositories_by_name.items():
                            if repo.clone_url == panel.repo_path:
                                selected_repo_name = repo_name
                                break
                    if selected_repo_name:
                        if repo_combo.findText(selected_repo_name) < 0:
                            repo_combo.addItem(selected_repo_name)
                        repo_combo.setCurrentText(selected_repo_name)

                    branch_combo = QComboBox()
                    branch_combo.setFixedHeight(self._terminal_cell_height)
                    branch_combo.setProperty("table_row_combo", True)
                    branch_combo.setMinimumContentsLength(16)
                    branches: list[str] = []
                    if selected_repo_name:
                        branches = self._branches_by_repo.get(selected_repo_name, [])
                    if branches:
                        branch_combo.addItems(branches)
                    selected_branch = self._pending_branch_by_terminal.get(panel.terminal_id, "")
                    if not selected_branch:
                        selected_branch = panel.branch
                    if selected_branch:
                        if branch_combo.findText(selected_branch) < 0:
                            branch_combo.addItem(selected_branch)
                        branch_combo.setCurrentText(selected_branch)

                    self.table.setCellWidget(row, 2, repo_combo)
                    self.table.setCellWidget(row, 3, branch_combo)
                    self._repo_combo_by_terminal[panel.terminal_id] = repo_combo
                    self._branch_combo_by_terminal[panel.terminal_id] = branch_combo

                    repo_combo.currentIndexChanged.connect(
                        lambda _index, terminal_id=panel.terminal_id: self._on_row_repo_changed(
                            terminal_id
                        )
                    )
                    branch_combo.currentIndexChanged.connect(
                        lambda _index, terminal_id=panel.terminal_id: self._on_row_branch_changed(
                            terminal_id
                        )
                    )

                if focus_row >= 0:
                    self.table.selectRow(focus_row)
            finally:
                self._updating_table = False

            self._select_template_card(dashboard.template_count)
            persist_snapshot()

        def _select_template_card(self, count: int) -> None:
            for template_count, card in self._template_cards.items():
                card.setChecked(template_count == count)

        def _template_preview(self, rows: int, cols: int) -> str:
            # Use pink/magenta squares for the terminal layout preview
            line = " ".join("â–ˆ" for _ in range(cols))
            return "\n".join(line for _ in range(rows))

        def _apply_visual_style(self) -> None:
            self.setStyleSheet(
                """
                QMainWindow {
                    background: #0f1724;
                }
                QLabel {
                    color: #e5edf7;
                    font-size: 13px;
                }
                QPushButton {
                    background: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 8px 16px;
                    color: #e5edf7;
                    font-weight: 500;
                }
                QPushButton:hover {
                    border-color: #60a5fa;
                    background: #243447;
                }
                QPushButton:pressed {
                    background: #1a2634;
                }
                QPushButton:disabled {
                    color: #64748b;
                    background: #141b27;
                    border-color: #1e293b;
                }
                QPushButton[action_btn="true"] {
                    background: #2563eb;
                    border: 1px solid #3b82f6;
                    color: #ffffff;
                    font-weight: 600;
                    padding: 10px 24px;
                    min-width: 100px;
                }
                QPushButton[action_btn="true"]:hover {
                    background: #3b82f6;
                    border-color: #60a5fa;
                }
                QPushButton[action_btn="true"]:pressed {
                    background: #1d4ed8;
                }
                QPushButton[secondary_btn="true"] {
                    background: #1e293b;
                    border: 1px solid #475569;
                    color: #e5edf7;
                    font-weight: 500;
                    padding: 8px 16px;
                    min-width: 120px;
                }
                QPushButton[secondary_btn="true"]:hover {
                    background: #26354a;
                    border-color: #64748b;
                }
                QPushButton[template_card="true"] {
                    text-align: center;
                    padding: 6px;
                    font-family: Consolas, 'Courier New', monospace;
                    font-size: 12px;
                    line-height: 1.2;
                    background: #162032;
                    border: 1px solid #334155;
                    border-radius: 10px;
                    color: #f472b6;
                }
                QPushButton[template_card="true"]:hover {
                    background: #1e293b;
                    border-color: #64748b;
                    color: #f9a8d4;
                }
                QPushButton[template_card="true"]:checked {
                    border: 2px solid #3b82f6;
                    background: #1d2b42;
                    color: #f472b6;
                }
                QPushButton[danger_btn="true"] {
                    background: #2d1f2d;
                    border: 1px solid #78354f;
                    color: #f9a8d4;
                    font-size: 16px;
                    font-weight: 700;
                    padding: 0;
                    min-width: 28px;
                    max-width: 28px;
                    min-height: 28px;
                    max-height: 28px;
                    border-radius: 6px;
                }
                QPushButton[danger_btn="true"]:hover {
                    background: #4a2040;
                    border: 1px solid #d9469a;
                    color: #fce7f3;
                }
                QPushButton[danger_btn="true"]:pressed {
                    background: #3a1830;
                }
                QLabel[row_title_label="true"] {
                    color: #e5edf7;
                    padding-left: 2px;
                }
                QLabel[grid_separator="true"] {
                    color: #9fb4d8;
                    font-weight: 700;
                    padding: 0 2px;
                }
                QLabel[grid_title_label="true"] {
                    color: #b8c8e6;
                    font-size: 12px;
                    font-weight: 600;
                    padding-right: 2px;
                }
                QLineEdit, QComboBox, QSpinBox {
                    background: #0f1724;
                    color: #e5edf7;
                    border: 1px solid #334155;
                    border-radius: 8px;
                    padding: 6px 8px;
                    min-height: 30px;
                    selection-background-color: #1d4ed8;
                    selection-color: #ffffff;
                }
                QComboBox QAbstractItemView {
                    background: #0f1724;
                    color: #e5edf7;
                    border: 1px solid #334155;
                    selection-background-color: #1d4ed8;
                    selection-color: #ffffff;
                }
                QComboBox[table_row_combo="true"] {
                    min-height: 0px;
                    padding-top: 2px;
                    padding-bottom: 2px;
                    border-radius: 6px;
                }
                QSpinBox {
                    padding-right: 20px;
                }
                QSpinBox[grid_compact="true"] {
                    min-height: 25px;
                    max-height: 25px;
                    padding-top: 1px;
                    padding-bottom: 1px;
                }
                QSpinBox::up-button, QSpinBox::down-button {
                    background: #182235;
                    border-left: 1px solid #334155;
                    width: 16px;
                }
                QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                    background: #223149;
                }
                QTableWidget {
                    background: #0f1724;
                    color: #e5edf7;
                    border: 1px solid #334155;
                    border-radius: 10px;
                    gridline-color: #263244;
                    selection-background-color: #1d4ed8;
                    selection-color: #ffffff;
                }
                QTableWidget::item {
                    color: #e5edf7;
                }
                QHeaderView::section {
                    background: #1a2230;
                    color: #e5edf7;
                    border: none;
                    border-right: 1px solid #334155;
                    padding: 8px;
                    font-weight: 600;
                }
                """
            )

        def closeEvent(self, event) -> None:  # type: ignore[override]
            persist_snapshot()
            event.accept()

    app = QApplication.instance() or QApplication(sys.argv)  # pragma: no cover
    window = RuntimeDashboardWindow()  # pragma: no cover
    window.show()
    app.exec()  # pragma: no cover
    persist_snapshot()  # pragma: no cover
    return int(ExitCode.SUCCESS)  # pragma: no cover



