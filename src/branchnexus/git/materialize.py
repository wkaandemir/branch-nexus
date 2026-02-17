"""Remote branch materialization (create local branch with upstream)."""

from __future__ import annotations

import logging as py_logging
import subprocess
from pathlib import Path, PurePosixPath

from branchnexus.errors import BranchNexusError, ExitCode

logger = py_logging.getLogger(__name__)


def _repo_arg(repo_path: str | Path | PurePosixPath) -> str:
    if isinstance(repo_path, PurePosixPath):
        return str(repo_path)

    normalized = str(repo_path).replace("\\", "/")
    if normalized.startswith("//mnt/"):
        normalized = normalized[1:]
    return normalized


def _run_git(repo: str, args: list[str], runner: callable) -> subprocess.CompletedProcess:
    return runner(["git", "-C", repo, *args], capture_output=True, text=True, check=False)


def _local_name(remote_branch: str) -> str:
    if "/" not in remote_branch:
        raise BranchNexusError(
            f"Invalid remote branch format: {remote_branch}",
            code=ExitCode.VALIDATION_ERROR,
            hint="Use branch names like origin/feature-x.",
        )
    return remote_branch.split("/", 1)[1]


def materialize_remote_branch(
    repo_path: str | Path | PurePosixPath,
    remote_branch: str,
    runner: callable = subprocess.run,
) -> str:
    repo = _repo_arg(repo_path)
    local_branch = _local_name(remote_branch)
    logger.debug(
        "Materializing remote branch repo=%s remote=%s local=%s",
        repo,
        remote_branch,
        local_branch,
    )

    exists = _run_git(repo, ["branch", "--list", local_branch], runner)
    if exists.returncode != 0:
        logger.error("Failed to check local branch existence repo=%s stderr=%s", repo, exists.stderr.strip())
        raise BranchNexusError(
            "Failed to check local branch existence.",
            code=ExitCode.GIT_ERROR,
            hint=(exists.stderr or "Inspect repository branch state.").strip(),
        )
    if exists.stdout.strip():
        logger.debug("Local branch already exists repo=%s branch=%s", repo, local_branch)
        return local_branch

    create = _run_git(repo, ["branch", "--track", local_branch, remote_branch], runner)
    if create.returncode == 0:
        logger.debug("Created local tracking branch repo=%s branch=%s", repo, local_branch)
        return local_branch

    logger.error(
        "Failed to create tracking branch repo=%s remote=%s stderr=%s",
        repo,
        remote_branch,
        create.stderr.strip(),
    )
    raise BranchNexusError(
        f"Failed to materialize remote branch {remote_branch}.",
        code=ExitCode.GIT_ERROR,
        hint=(create.stderr or "Check remote branch existence and tracking permissions.").strip(),
    )
