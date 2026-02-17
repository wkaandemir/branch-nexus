from __future__ import annotations

import subprocess

import pytest

from branchnexus.docker.runtime import DockerRuntime
from branchnexus.errors import BranchNexusError


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_branch_isolated_services_start_without_collision() -> None:
    commands: list[list[str]] = []

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        commands.append(cmd)
        return _cp(0)

    runtime = DockerRuntime()
    runtime.register_branch("feature/a", [5433])
    runtime.register_branch("feature/b", [5434])
    runtime.up("feature/a", runner=runner)
    runtime.up("feature/b", runner=runner)

    assert any(cmd[-2:] == ["up", "-d"] for cmd in commands)


def test_port_collision_is_blocked() -> None:
    runtime = DockerRuntime()
    runtime.register_branch("a", [5432])
    with pytest.raises(BranchNexusError):
        runtime.register_branch("b", [5432])


def test_session_cleanup_applies_to_docker_policy() -> None:
    commands: list[list[str]] = []

    def runner(cmd: list[str], **_: object) -> subprocess.CompletedProcess:
        commands.append(cmd)
        return _cp(0)

    runtime = DockerRuntime()
    runtime.register_branch("a", [5433])
    runtime.register_branch("b", [5434])

    removed = runtime.cleanup(policy="session", runner=runner)
    assert len(removed) == 2
    assert all(cmd[-2:] == ["down", "-v"] for cmd in commands)
