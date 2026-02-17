"""In-memory terminal lifecycle orchestration for runtime-v2."""

from __future__ import annotations

import logging as py_logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Protocol

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.git.materialize import materialize_remote_branch
from branchnexus.git.remote_provider import CombinedBranchSet, fetch_and_list
from branchnexus.terminal.models import RuntimeKind, TerminalInstance, TerminalSpec, TerminalState
from branchnexus.terminal.pty_backend import PtyBackend

logger = py_logging.getLogger(__name__)


class DirtySwitchDecision(str, Enum):
    CANCEL = "cancel"
    PRESERVE = "preserve"
    CLEAN = "clean"


@dataclass(frozen=True)
class TerminalEvent:
    terminal_id: str
    step: str
    message: str


class BranchProvider(Protocol):
    def __call__(self, repo_path: str) -> CombinedBranchSet: ...


class Materializer(Protocol):
    def __call__(
        self,
        repo_path: str | Path | PurePosixPath,
        branch: str,
        runner: object = ...,
    ) -> str: ...


DirtyChecker = Callable[[TerminalInstance], bool]
DirtyResolver = Callable[[TerminalInstance], DirtySwitchDecision | str]


class TerminalService:
    def __init__(
        self,
        *,
        max_terminals: int = 16,
        default_runtime: RuntimeKind = RuntimeKind.WSL,
        pty_backend: PtyBackend | None = None,
        branch_provider: BranchProvider | None = None,
        materializer: Materializer | None = None,
    ) -> None:
        if max_terminals < 2 or max_terminals > 16:
            raise BranchNexusError(
                f"Invalid max terminal count: {max_terminals}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Use a value between 2 and 16.",
            )
        self.default_runtime = default_runtime
        self.max_terminals = max_terminals
        self._pty_backend = pty_backend
        self._branch_provider = branch_provider or fetch_and_list
        self._materializer = materializer or materialize_remote_branch
        self._instances: dict[str, TerminalInstance] = {}
        self._events: list[TerminalEvent] = []

    def list_instances(self) -> list[TerminalInstance]:
        return [self._instances[key] for key in sorted(self._instances)]

    def list_events(self) -> list[TerminalEvent]:
        return list(self._events)

    def clear_events(self) -> None:
        self._events.clear()
        logger.info("runtime-event terminal=* step=clear-events message=Terminal events cleared.")

    def record_event(self, terminal_id: str, step: str, message: str) -> None:
        self._record(terminal_id, step, message)

    def create(self, spec: TerminalSpec) -> TerminalInstance:
        if spec.terminal_id in self._instances:
            raise BranchNexusError(
                f"Terminal already exists: {spec.terminal_id}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Use a unique terminal id.",
            )
        if len(self._instances) >= self.max_terminals:
            raise BranchNexusError(
                f"Terminal limit reached: {self.max_terminals}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Close another terminal before creating a new one.",
            )
        resolved_runtime = spec.runtime or self.default_runtime
        resolved_spec = replace(spec, runtime=resolved_runtime)
        instance = TerminalInstance(spec=resolved_spec)
        self._instances[spec.terminal_id] = instance
        self._record(spec.terminal_id, "create", f"Created terminal '{spec.title}'.")
        return instance

    def create_terminal(
        self,
        *,
        terminal_id: str,
        title: str,
        runtime: RuntimeKind | None = None,
        repo_path: str = "",
        branch: str = "",
    ) -> TerminalInstance:
        return self.create(
            TerminalSpec(
                terminal_id=terminal_id,
                title=title,
                runtime=runtime or self.default_runtime,
                repo_path=repo_path,
                branch=branch,
            )
        )

    def start(self, terminal_id: str) -> TerminalInstance:
        instance = self._must_get(terminal_id)
        if self._pty_backend is not None and instance.metadata.get("pty_attached") != "true":
            self._pty_backend.start(
                terminal_id,
                runtime=instance.spec.runtime,
                cwd=instance.spec.repo_path or None,
            )
            instance.metadata["pty_attached"] = "true"
        instance.state = TerminalState.RUNNING
        self._record(terminal_id, "start", "Terminal is running.")
        return instance

    def stop(self, terminal_id: str) -> TerminalInstance:
        instance = self._must_get(terminal_id)
        if self._pty_backend is not None and instance.metadata.get("pty_attached") == "true":
            try:
                self._pty_backend.stop(terminal_id)
            except BranchNexusError as exc:
                instance.state = TerminalState.FAILED
                instance.metadata["failure_reason"] = exc.message
                self._record(terminal_id, "stop-failed", exc.message)
                raise
            instance.metadata.pop("pty_attached", None)
        instance.state = TerminalState.STOPPED
        self._record(terminal_id, "stop", "Terminal stopped.")
        return instance

    def restart(self, terminal_id: str) -> TerminalInstance:
        self.stop(terminal_id)
        return self.start(terminal_id)

    def mark_failed(self, terminal_id: str, reason: str = "") -> TerminalInstance:
        instance = self._must_get(terminal_id)
        instance.state = TerminalState.FAILED
        if reason:
            instance.metadata["failure_reason"] = reason
        self._record(terminal_id, "failed", reason or "Terminal failed.")
        return instance

    def remove(self, terminal_id: str, *, cleanup: str = "preserve") -> None:
        if cleanup not in {"preserve", "clean"}:
            raise BranchNexusError(
                f"Invalid cleanup option: {cleanup}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Use preserve or clean cleanup policy.",
            )
        instance = self._must_get(terminal_id)
        if instance.state == TerminalState.RUNNING:
            self.stop(terminal_id)
        instance.metadata["cleanup"] = cleanup
        del self._instances[terminal_id]
        self._record(terminal_id, "remove", f"Terminal removed ({cleanup}).")

    def list_branches(self, repo_path: str) -> CombinedBranchSet:
        if not repo_path.strip():
            raise BranchNexusError(
                "Repository path is required.",
                code=ExitCode.VALIDATION_ERROR,
                hint="Select a repository before loading branches.",
            )
        payload = self._branch_provider(repo_path.strip())
        if isinstance(payload, CombinedBranchSet):
            return payload
        local = sorted(getattr(payload, "local", []))
        remote = sorted(getattr(payload, "remote", []))
        warning = str(getattr(payload, "warning", ""))
        return CombinedBranchSet(local=local, remote=remote, warning=warning)

    def switch_context(
        self,
        terminal_id: str,
        *,
        repo_path: str,
        branch: str,
        runtime: RuntimeKind | None = None,
        dirty_checker: DirtyChecker | None = None,
        dirty_resolver: DirtyResolver | None = None,
    ) -> TerminalInstance:
        if not repo_path.strip():
            raise BranchNexusError(
                "Repository path is required.",
                code=ExitCode.VALIDATION_ERROR,
                hint="Select a repository for terminal switch.",
            )
        if not branch.strip():
            raise BranchNexusError(
                "Branch is required.",
                code=ExitCode.VALIDATION_ERROR,
                hint="Select a branch for terminal switch.",
            )
        instance = self._must_get(terminal_id)
        previous_spec = instance.spec
        previous_state = instance.state
        self._record(terminal_id, "switch-start", "Switching repo/branch context.")

        if dirty_checker and dirty_checker(instance):
            decision = _normalize_dirty_decision(
                dirty_resolver(instance) if dirty_resolver else DirtySwitchDecision.CANCEL
            )
            if decision == DirtySwitchDecision.CANCEL:
                self._record(terminal_id, "switch-cancel", "Dirty state cancelled switch.")
                raise BranchNexusError(
                    "Switch cancelled due to dirty worktree.",
                    code=ExitCode.VALIDATION_ERROR,
                    hint="Commit/stash changes or choose preserve/clean option.",
                )
            instance.metadata["dirty_switch"] = decision.value
            self._record(terminal_id, "switch-dirty", f"Dirty switch decision: {decision.value}.")

        next_repo = repo_path.strip()
        next_branch = branch.strip()
        if next_branch.startswith("origin/"):
            next_branch = self._materializer(next_repo, next_branch)
            self._record(terminal_id, "switch-materialize", f"Materialized remote branch to {next_branch}.")

        next_runtime = runtime or instance.spec.runtime or self.default_runtime
        should_reopen = previous_state == TerminalState.RUNNING
        if should_reopen:
            self._record(terminal_id, "switch-stop-old", "Stopping current terminal process.")
            self.stop(terminal_id)

        instance.spec = replace(
            instance.spec,
            repo_path=next_repo,
            branch=next_branch,
            runtime=next_runtime,
        )

        try:
            self._record(terminal_id, "switch-start-new", "Starting terminal with new context.")
            self.start(terminal_id)
        except Exception as exc:
            instance.spec = previous_spec
            instance.state = previous_state
            self._record(terminal_id, "switch-revert", "Switch failed; restoring previous context.")
            if should_reopen and previous_state == TerminalState.RUNNING:
                try:
                    self.start(terminal_id)
                except Exception:
                    self.mark_failed(terminal_id, "Failed to restore previous PTY session.")
            if isinstance(exc, BranchNexusError):
                raise
            raise BranchNexusError(
                "Failed to switch terminal context.",
                code=ExitCode.RUNTIME_ERROR,
                hint=str(exc) or "Inspect switch logs and retry.",
            ) from exc

        self._record(terminal_id, "switch-complete", "Terminal switch completed.")
        return instance

    def _must_get(self, terminal_id: str) -> TerminalInstance:
        instance = self._instances.get(terminal_id)
        if instance is None:
            raise BranchNexusError(
                f"Terminal not found: {terminal_id}",
                code=ExitCode.VALIDATION_ERROR,
                hint="Select an existing terminal.",
            )
        return instance

    def _record(self, terminal_id: str, step: str, message: str) -> None:
        self._events.append(TerminalEvent(terminal_id=terminal_id, step=step, message=message))
        logger.info("runtime-event terminal=%s step=%s message=%s", terminal_id, step, message)


def _normalize_dirty_decision(value: DirtySwitchDecision | str) -> DirtySwitchDecision:
    if isinstance(value, DirtySwitchDecision):
        return value
    normalized = str(value).strip().lower()
    if normalized == DirtySwitchDecision.CLEAN.value:
        return DirtySwitchDecision.CLEAN
    if normalized == DirtySwitchDecision.PRESERVE.value:
        return DirtySwitchDecision.PRESERVE
    return DirtySwitchDecision.CANCEL
