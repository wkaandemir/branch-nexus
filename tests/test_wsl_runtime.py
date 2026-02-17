from __future__ import annotations

import subprocess

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.runtime.wsl_runtime import WslRuntime

pytestmark = pytest.mark.critical_regression


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_distribution_switch_reinitializes_generation() -> None:
    runtime = WslRuntime("Ubuntu", runner=lambda *args, **kwargs: _cp(0))
    initial = runtime.generation
    runtime.switch_distribution("Debian")
    assert runtime.generation == initial + 1
    assert runtime.distribution == "Debian"


def test_runtime_retries_transient_wsl_failures() -> None:
    attempts = {"count": 0}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return _cp(1, stderr="WSL temporary connection reset")
        return _cp(0, stdout="ok")

    runtime = WslRuntime("Ubuntu", runner=runner, max_retries=2)
    result = runtime.run(["echo", "ok"])
    assert result.returncode == 0
    assert attempts["count"] == 2


def test_runtime_does_not_retry_non_transient_wsl_prefixed_errors() -> None:
    attempts = {"count": 0}

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        attempts["count"] += 1
        return _cp(1, stderr="WSL failed to launch shell")

    runtime = WslRuntime("Ubuntu", runner=runner, max_retries=3)
    with pytest.raises(BranchNexusError):
        runtime.run(["echo", "ok"])

    assert attempts["count"] == 1


def test_runtime_timeout_raises_actionable_error() -> None:
    def runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess:
        raise subprocess.TimeoutExpired(cmd="sleep", timeout=1)

    runtime = WslRuntime("Ubuntu", runner=runner)
    with pytest.raises(BranchNexusError):
        runtime.run(["sleep", "10"])


def test_runtime_cancel_prevents_execution() -> None:
    runtime = WslRuntime("Ubuntu", runner=lambda *args, **kwargs: _cp(0))
    with pytest.raises(BranchNexusError):
        runtime.run(["echo", "x"], cancelled=lambda: True)
