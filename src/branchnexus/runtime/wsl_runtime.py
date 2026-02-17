"""Hardened WSL runtime executor with retry and timeout controls."""

from __future__ import annotations

import logging as py_logging
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.runtime.wsl_discovery import build_wsl_command

logger = py_logging.getLogger(__name__)

_TRANSIENT_ERROR_MARKERS = (
    "connection reset",
    "connection refused",
    "network is unreachable",
    "temporar",
    "timed out",
    "timeout",
    "resource temporarily unavailable",
)

_TRANSIENT_WSL_CONTEXT_MARKERS = (
    "failed to connect",
    "cannot connect",
    "connection",
    "service unavailable",
)


@dataclass
class RuntimeResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


def _is_transient_wsl_error(stderr: str) -> bool:
    text = stderr.lower()
    if any(marker in text for marker in _TRANSIENT_ERROR_MARKERS):
        return True
    return "wsl" in text and any(marker in text for marker in _TRANSIENT_WSL_CONTEXT_MARKERS)


class WslRuntime:
    def __init__(
        self,
        distribution: str,
        *,
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self.distribution = distribution
        self.runner = runner
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._generation = 0

    @property
    def generation(self) -> int:
        return self._generation

    def switch_distribution(self, distribution: str) -> None:
        self.distribution = distribution
        self._generation += 1
        logger.info("Switched WSL distribution to %s (generation=%s)", distribution, self._generation)

    def run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> RuntimeResult:
        if cancelled and cancelled():
            logger.warning("Runtime execution cancelled before command start")
            raise BranchNexusError(
                "Runtime command was cancelled.",
                code=ExitCode.RUNTIME_ERROR,
                hint="Retry the command when ready.",
            )

        last_error: BranchNexusError | None = None
        for attempt in range(self.max_retries + 1):
            try:
                wrapped = build_wsl_command(self.distribution, list(command))
                logger.debug(
                    "Running WSL command attempt=%s/%s command=%s",
                    attempt + 1,
                    self.max_retries + 1,
                    wrapped,
                )
                completed = self.runner(
                    wrapped,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=timeout_seconds or self.timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                logger.error("WSL command timed out command=%s", command)
                raise BranchNexusError(
                    "WSL command timed out.",
                    code=ExitCode.RUNTIME_ERROR,
                    hint="Increase timeout or inspect hanging process.",
                ) from exc

            if completed.returncode == 0:
                logger.debug("WSL command succeeded attempt=%s command=%s", attempt + 1, wrapped)
                return RuntimeResult(
                    command=wrapped,
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )

            stderr = (completed.stderr or "").lower()
            transient = _is_transient_wsl_error(stderr)
            logger.warning(
                "WSL command failed attempt=%s transient=%s stderr=%s",
                attempt + 1,
                transient,
                completed.stderr.strip(),
            )
            last_error = BranchNexusError(
                "WSL command failed.",
                code=ExitCode.RUNTIME_ERROR,
                hint=completed.stderr.strip() or "Check WSL runtime and retry.",
            )
            if not transient:
                break

        if last_error:
            logger.error("WSL command exhausted retries command=%s", command)
            raise last_error
        logger.error("WSL command failed unexpectedly without captured error command=%s", command)
        raise BranchNexusError(
            "WSL command failed unexpectedly.",
            code=ExitCode.RUNTIME_ERROR,
            hint="Inspect runtime logs and retry.",
        )
