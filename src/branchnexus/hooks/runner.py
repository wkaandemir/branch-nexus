"""Panel command hooks runner."""

from __future__ import annotations

import logging as py_logging
import shlex
import subprocess
from dataclasses import dataclass

logger = py_logging.getLogger(__name__)


@dataclass(frozen=True)
class HookExecution:
    command: str
    success: bool
    returncode: int
    output: str


@dataclass
class HookRunResult:
    pane: int
    executions: list[HookExecution]

    @property
    def has_failures(self) -> bool:
        return any(not execution.success for execution in self.executions)


class HookRunner:
    def __init__(
        self,
        timeout_seconds: float = 30.0,
        *,
        trusted_config: bool = True,
        allow_command_prefixes: list[str] | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.trusted_config = trusted_config
        self.allow_command_prefixes = [item.strip() for item in (allow_command_prefixes or []) if item.strip()]

    def _is_command_allowed(self, command: str) -> bool:
        if self.trusted_config:
            return True
        try:
            argv = shlex.split(command)
        except ValueError:
            return False
        if not argv:
            return False
        if not self.allow_command_prefixes:
            return False
        return argv[0] in set(self.allow_command_prefixes)

    def run(
        self,
        *,
        pane: int,
        commands: list[str],
        runner: callable = subprocess.run,
    ) -> HookRunResult:
        executions: list[HookExecution] = []
        logger.debug("Running %s hook commands for pane=%s", len(commands), pane)
        for command in commands:
            if not self._is_command_allowed(command):
                logger.warning("Hook command blocked by policy pane=%s command=%s", pane, command)
                executions.append(
                    HookExecution(
                        command=command,
                        success=False,
                        returncode=126,
                        output="Command blocked by hook trust policy.",
                    )
                )
                continue
            try:
                logger.debug("Executing hook command pane=%s command=%s", pane, command)
                argv = ["bash", "-lc", command]
                completed = runner(
                    argv,
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                )
                success = completed.returncode == 0
                output = f"{completed.stdout}{completed.stderr}".strip()
                if not success:
                    logger.warning(
                        "Hook command failed pane=%s returncode=%s command=%s",
                        pane,
                        completed.returncode,
                        command,
                    )
                executions.append(
                    HookExecution(
                        command=command,
                        success=success,
                        returncode=completed.returncode,
                        output=output,
                    )
                )
            except subprocess.TimeoutExpired:
                logger.error("Hook command timed out pane=%s command=%s", pane, command)
                executions.append(
                    HookExecution(
                        command=command,
                        success=False,
                        returncode=124,
                        output="Command timed out.",
                    )
                )
        return HookRunResult(pane=pane, executions=executions)
