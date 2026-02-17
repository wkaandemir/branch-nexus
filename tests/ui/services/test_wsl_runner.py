from __future__ import annotations

import subprocess
import time

import pytest

import branchnexus.ui.services.wsl_runner as wsl_runner


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_wsl_script_emits_verbose_lines(monkeypatch) -> None:
    emitted: list[str] = []

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return _cp(0, stdout="ok")

    monkeypatch.setattr(wsl_runner.subprocess, "run", fake_run)
    wsl_runner.run_wsl_script(
        distribution="Ubuntu",
        script="echo ok",
        step="unit-test",
        env={"PATH": "/usr/bin"},
        verbose_sink=emitted.append,
    )
    assert any("[RUN]" in line for line in emitted)
    assert any("[OK]" in line for line in emitted)


def test_run_with_heartbeat_emits_wait(monkeypatch) -> None:
    emitted: list[str] = []
    monkeypatch.setattr(wsl_runner, "COMMAND_HEARTBEAT_SECONDS", 1)

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        time.sleep(1.2)
        return _cp(0, stdout="ok")

    monkeypatch.setattr(wsl_runner.subprocess, "run", fake_run)
    result = wsl_runner.run_with_heartbeat(
        command=["wsl.exe", "-d", "Ubuntu", "--", "bash", "-lc", "echo ok"],
        env=None,
        timeout_seconds=300,
        step="heartbeat-test",
        verbose_sink=emitted.append,
    )
    assert result.returncode == 0
    assert any("[WAIT]" in line and "heartbeat-test" in line for line in emitted)


def test_run_wsl_script_success_uses_bash_lc(monkeypatch) -> None:
    seen: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["command"] = command
        seen["env"] = kwargs.get("env")
        return _cp(0, stdout="ok")

    monkeypatch.setattr(wsl_runner.subprocess, "run", fake_run)
    result = wsl_runner.run_wsl_script(
        distribution="Ubuntu-22.04",
        script="echo ok",
        step="unit-step",
        env={"A": "B"},
    )
    assert result.returncode == 0
    assert seen["command"] == ["wsl.exe", "-d", "Ubuntu-22.04", "--", "bash", "-lc", "echo ok"]
    assert seen["env"] == {"A": "B"}


def test_run_wsl_script_failure_raises_with_step_context(monkeypatch) -> None:
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        return _cp(1, stderr="boom")

    monkeypatch.setattr(wsl_runner.subprocess, "run", fake_run)
    with pytest.raises(wsl_runner.BranchNexusError) as exc:
        wsl_runner.run_wsl_script(
            distribution="Ubuntu",
            script="false",
            step="failing-step",
        )
    assert exc.value.message == "Runtime WSL hazirlik adimi basarisiz: failing-step"
    assert exc.value.hint == "boom"


def test_run_wsl_script_timeout_raises_with_step_context(monkeypatch) -> None:
    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, timeout=kwargs.get("timeout", 300))

    monkeypatch.setattr(wsl_runner.subprocess, "run", fake_run)
    with pytest.raises(wsl_runner.BranchNexusError) as exc:
        wsl_runner.run_wsl_script(
            distribution="Ubuntu",
            script="sleep 999",
            step="timeout-step",
        )
    assert exc.value.message == "Runtime WSL hazirlik adimi zaman asimina ugradi: timeout-step"
