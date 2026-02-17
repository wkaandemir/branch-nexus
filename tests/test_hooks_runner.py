from __future__ import annotations

import subprocess

from branchnexus.hooks.runner import HookRunner


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_hooks_runner_executes_all_commands_and_reports_failures() -> None:
    responses = {
        "echo ok": _cp(0, stdout="ok\n"),
        "false": _cp(1, stderr="bad\n"),
    }

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        assert cmd[:2] == ["bash", "-lc"]
        return responses[cmd[2]]

    result = HookRunner(timeout_seconds=1.0).run(pane=1, commands=["echo ok", "false"], runner=runner)
    assert len(result.executions) == 2
    assert result.executions[0].success is True
    assert result.executions[1].success is False
    assert result.has_failures is True


def test_hooks_runner_blocks_untrusted_commands_when_policy_restricted() -> None:
    calls: list[list[str]] = []

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        calls.append(cmd)
        return _cp(0, stdout="ok\n")

    hook_runner = HookRunner(
        timeout_seconds=1.0,
        trusted_config=False,
        allow_command_prefixes=["echo"],
    )
    result = hook_runner.run(
        pane=1,
        commands=["echo ok", "rm -rf /tmp/demo"],
        runner=runner,
    )

    assert len(result.executions) == 2
    assert result.executions[0].success is True
    assert result.executions[1].success is False
    assert result.executions[1].returncode == 126
    assert calls == [["bash", "-lc", "echo ok"]]
