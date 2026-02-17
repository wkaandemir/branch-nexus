"""Hooks runner edge case tests."""

from __future__ import annotations

import subprocess

from branchnexus.hooks.runner import HookRunner


def test_hooks_runner_empty_command_list() -> None:
    runner = HookRunner()
    result = runner.run(pane=1, commands=[])
    assert len(result.executions) == 0


def test_hooks_runner_blocks_shell_metacharacters() -> None:
    def mock_runner(*args, **kwargs):
        class MockResult:
            returncode = 0
            stdout = ""
            stderr = ""

        return MockResult()

    hook_runner = HookRunner(trusted_config=False, allow_command_prefixes=["git"])
    result = hook_runner.run(pane=1, commands=["echo $HOME"], runner=mock_runner)
    assert result.executions[0].success is False
    assert result.executions[0].returncode == 126


def test_hooks_runner_timeout_returns_error() -> None:
    def mock_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired("cmd", 0.001)

    hook_runner = HookRunner(timeout_seconds=0.001)
    result = hook_runner.run(pane=1, commands=["sleep 10"], runner=mock_runner)
    assert result.executions[0].returncode == 124
    assert "timed out" in result.executions[0].output.lower()


def test_hooks_runner_blocks_invalid_prefix() -> None:
    def mock_runner(*args, **kwargs):
        class MockResult:
            returncode = 0
            stdout = ""
            stderr = ""

        return MockResult()

    hook_runner = HookRunner(trusted_config=False, allow_command_prefixes=["git"])
    result = hook_runner.run(pane=1, commands=["npm install"], runner=mock_runner)
    assert result.executions[0].success is False
    assert "blocked" in result.executions[0].output.lower()
