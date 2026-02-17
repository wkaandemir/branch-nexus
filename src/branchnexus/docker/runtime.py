"""Docker runtime for branch-isolated service environments."""

from __future__ import annotations

import logging as py_logging
import re
import subprocess
from dataclasses import dataclass, field

from branchnexus.errors import BranchNexusError, ExitCode

_SANITIZE = re.compile(r"[^A-Za-z0-9_-]+")
logger = py_logging.getLogger(__name__)


@dataclass
class DockerSession:
    project: str
    branch: str
    ports: list[int] = field(default_factory=list)


class DockerRuntime:
    def __init__(self, compose_file: str = "docker-compose.yml") -> None:
        self.compose_file = compose_file
        self._sessions: dict[str, DockerSession] = {}

    def _project_name(self, branch: str) -> str:
        cleaned = _SANITIZE.sub("-", branch).strip("-").lower()
        return f"bnx-{cleaned or 'default'}"

    def register_branch(self, branch: str, ports: list[int]) -> DockerSession:
        used_ports = {port for session in self._sessions.values() for port in session.ports}
        collision = used_ports.intersection(ports)
        if collision:
            logger.error("Port collision for branch=%s ports=%s", branch, sorted(collision))
            raise BranchNexusError(
                f"Port collision detected: {sorted(collision)}",
                code=ExitCode.RUNTIME_ERROR,
                hint="Use different ports for branch-isolated services.",
            )

        project = self._project_name(branch)
        session = DockerSession(project=project, branch=branch, ports=list(ports))
        self._sessions[branch] = session
        logger.debug("Registered docker session branch=%s project=%s", branch, project)
        return session

    def up(self, branch: str, *, runner: callable = subprocess.run) -> list[str]:
        if branch not in self._sessions:
            self.register_branch(branch, [])
        session = self._sessions[branch]
        cmd = [
            "docker",
            "compose",
            "-f",
            self.compose_file,
            "-p",
            session.project,
            "up",
            "-d",
        ]
        logger.debug("Running docker up command=%s", cmd)
        result = runner(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error("docker compose up failed branch=%s stderr=%s", branch, result.stderr.strip())
            raise BranchNexusError(
                f"Failed to start docker services for branch {branch}",
                code=ExitCode.RUNTIME_ERROR,
                hint=result.stderr.strip() or "Inspect docker compose output.",
            )
        return cmd

    def down(self, branch: str, *, runner: callable = subprocess.run) -> list[str]:
        if branch not in self._sessions:
            logger.debug("docker down skipped; no session for branch=%s", branch)
            return []
        session = self._sessions[branch]
        cmd = [
            "docker",
            "compose",
            "-f",
            self.compose_file,
            "-p",
            session.project,
            "down",
            "-v",
        ]
        logger.debug("Running docker down command=%s", cmd)
        result = runner(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error("docker compose down failed branch=%s stderr=%s", branch, result.stderr.strip())
            raise BranchNexusError(
                f"Failed to stop docker services for branch {branch}",
                code=ExitCode.RUNTIME_ERROR,
                hint=result.stderr.strip() or "Inspect docker compose output.",
            )
        return cmd

    def cleanup(self, *, policy: str, runner: callable = subprocess.run) -> list[list[str]]:
        if policy == "persistent":
            return []
        commands: list[list[str]] = []
        for branch in list(self._sessions.keys()):
            commands.append(self.down(branch, runner=runner))
        return commands
