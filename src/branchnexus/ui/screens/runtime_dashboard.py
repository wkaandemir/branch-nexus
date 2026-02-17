"""Runtime-v2 split-pane dashboard domain model."""

from __future__ import annotations

from dataclasses import dataclass

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.presets import resolve_terminal_template, validate_terminal_count
from branchnexus.terminal import DirtySwitchDecision, RuntimeKind, TerminalService, TerminalSpec


@dataclass(frozen=True)
class RuntimePanel:
    terminal_id: str
    title: str
    runtime: RuntimeKind
    repo_path: str
    branch: str
    focused: bool = False


class RuntimeDashboardScreen:
    def __init__(
        self,
        service: TerminalService,
        *,
        template: str | int = "4",
        custom_terminal_count: int | None = None,
        default_runtime: RuntimeKind = RuntimeKind.WSL,
    ) -> None:
        self.service = service
        self.default_runtime = default_runtime
        self.template_count = resolve_terminal_template(template, custom_value=custom_terminal_count)
        self._focused_terminal_id = ""

    def bootstrap(self) -> None:
        self._sync_terminal_count(self.template_count)
        panels = self.service.list_instances()
        if panels:
            self._focused_terminal_id = panels[0].spec.terminal_id

    def set_template(self, template: str | int, *, custom_terminal_count: int | None = None) -> int:
        self.template_count = resolve_terminal_template(template, custom_value=custom_terminal_count)
        self._sync_terminal_count(self.template_count)
        return self.template_count

    def add_terminal(
        self,
        *,
        runtime: RuntimeKind | None = None,
        repo_path: str = "",
        branch: str = "main",
    ):
        if len(self.service.list_instances()) >= self.service.max_terminals:
            raise BranchNexusError(
                "Maximum terminal count reached.",
                code=ExitCode.VALIDATION_ERROR,
                hint="Select a lower template or remove an existing terminal.",
            )
        terminal_id = self._next_terminal_id()
        title = f"Terminal {len(self.service.list_instances()) + 1}"
        instance = self.service.create(
            TerminalSpec(
                terminal_id=terminal_id,
                title=title,
                runtime=runtime or self.default_runtime,
                repo_path=repo_path.strip(),
                branch=branch.strip(),
            )
        )
        self.service.start(terminal_id)
        self.focus_terminal(terminal_id)
        return instance

    def remove_terminal(self, terminal_id: str, *, cleanup: str = "preserve") -> None:
        self.service.remove(terminal_id, cleanup=cleanup)
        if self._focused_terminal_id == terminal_id:
            remaining = self.service.list_instances()
            self._focused_terminal_id = remaining[0].spec.terminal_id if remaining else ""

    def change_repo_branch(
        self,
        terminal_id: str,
        *,
        repo_path: str,
        branch: str,
        runtime: RuntimeKind | None = None,
        dirty_checker=None,
        dirty_resolver=None,
    ):
        instance = self.service.switch_context(
            terminal_id,
            repo_path=repo_path,
            branch=branch,
            runtime=runtime,
            dirty_checker=dirty_checker,
            dirty_resolver=dirty_resolver,
        )
        self.focus_terminal(terminal_id)
        return instance

    def focus_terminal(self, terminal_id: str) -> None:
        if terminal_id not in {item.spec.terminal_id for item in self.service.list_instances()}:
            raise BranchNexusError(
                f"Terminal not found: {terminal_id}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Select a terminal from active panel list.",
            )
        self._focused_terminal_id = terminal_id

    def list_panels(self) -> list[RuntimePanel]:
        return [
            RuntimePanel(
                terminal_id=instance.spec.terminal_id,
                title=instance.spec.title,
                runtime=instance.spec.runtime,
                repo_path=instance.spec.repo_path,
                branch=instance.spec.branch,
                focused=instance.spec.terminal_id == self._focused_terminal_id,
            )
            for instance in self.service.list_instances()
        ]

    def event_lines(self) -> list[str]:
        return [f"{event.terminal_id}:{event.step}:{event.message}" for event in self.service.list_events()]

    @property
    def focused_terminal_id(self) -> str:
        return self._focused_terminal_id

    def snapshot(self, *, layout: str = "grid") -> dict[str, object]:
        return {
            "layout": layout,
            "template_count": self.template_count,
            "focused_terminal_id": self._focused_terminal_id,
            "terminals": [
                {
                    "terminal_id": item.spec.terminal_id,
                    "title": item.spec.title,
                    "runtime": item.spec.runtime.value,
                    "repo_path": item.spec.repo_path,
                    "branch": item.spec.branch,
                }
                for item in self.service.list_instances()
            ],
        }

    def restore_snapshot(self, snapshot: dict[str, object]) -> bool:
        terminals = snapshot.get("terminals")
        if not isinstance(terminals, list):
            return False
        if not terminals:
            return False

        try:
            target_count = validate_terminal_count(len(terminals))
        except BranchNexusError:
            return False

        parsed_specs: list[TerminalSpec] = []
        seen_ids: set[str] = set()
        for item in terminals:
            if not isinstance(item, dict):
                return False
            terminal_id = str(item.get("terminal_id", "")).strip()
            title = str(item.get("title", terminal_id or "Terminal")).strip()
            repo_path = str(item.get("repo_path", "")).strip()
            branch = str(item.get("branch", "")).strip()
            runtime_raw = str(item.get("runtime", RuntimeKind.WSL.value)).strip().lower()
            runtime = RuntimeKind.WSL
            if runtime_raw == RuntimeKind.POWERSHELL.value:
                runtime = RuntimeKind.POWERSHELL
            elif runtime_raw != RuntimeKind.WSL.value:
                return False
            if not terminal_id:
                return False
            if terminal_id in seen_ids:
                return False
            seen_ids.add(terminal_id)
            parsed_specs.append(
                TerminalSpec(
                    terminal_id=terminal_id,
                    title=title,
                    runtime=runtime,
                    repo_path=repo_path,
                    branch=branch,
                )
            )

        existing_instances = list(self.service.list_instances())
        existing_focus = self._focused_terminal_id
        try:
            for instance in existing_instances:
                self.service.remove(instance.spec.terminal_id, cleanup="preserve")

            self.template_count = target_count
            for spec in parsed_specs:
                self.service.create(spec)
                self.service.start(spec.terminal_id)
        except BranchNexusError:
            for instance in list(self.service.list_instances()):
                self.service.remove(instance.spec.terminal_id, cleanup="preserve")
            for previous in existing_instances:
                self.service.create(previous.spec)
                self.service.start(previous.spec.terminal_id)
            self._focused_terminal_id = existing_focus
            return False

        focused = str(snapshot.get("focused_terminal_id", "")).strip()
        if focused:
            try:
                self.focus_terminal(focused)
            except BranchNexusError:
                self._focused_terminal_id = self.service.list_instances()[0].spec.terminal_id
        else:
            self._focused_terminal_id = self.service.list_instances()[0].spec.terminal_id
        return True

    def _sync_terminal_count(self, count: int) -> None:
        target = validate_terminal_count(count)
        current = self.service.list_instances()

        while len(current) < target:
            self.add_terminal(runtime=self.default_runtime, branch="")
            current = self.service.list_instances()

        while len(current) > target:
            self.remove_terminal(current[-1].spec.terminal_id, cleanup="preserve")
            current = self.service.list_instances()

        if current and not self._focused_terminal_id:
            self._focused_terminal_id = current[0].spec.terminal_id

    def _next_terminal_id(self) -> str:
        existing = {item.spec.terminal_id for item in self.service.list_instances()}
        index = 1
        while True:
            candidate = f"t{index}"
            if candidate not in existing:
                return candidate
            index += 1


def dirty_choice_from_dialog(choice: str) -> DirtySwitchDecision:
    normalized = choice.strip().lower()
    if normalized in {"temizleyerek devam", "clean", DirtySwitchDecision.CLEAN.value}:
        return DirtySwitchDecision.CLEAN
    if normalized in {"koruyarak devam", "preserve", DirtySwitchDecision.PRESERVE.value}:
        return DirtySwitchDecision.PRESERVE
    return DirtySwitchDecision.CANCEL
