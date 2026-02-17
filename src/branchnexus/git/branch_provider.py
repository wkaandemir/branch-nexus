"""Local branch provider."""

from __future__ import annotations

import logging as py_logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from branchnexus.errors import BranchNexusError, ExitCode

logger = py_logging.getLogger(__name__)


@dataclass
class BranchListResult:
    branches: list[str]
    warning: str = ""


def _run_git(repo: Path, args: list[str], runner: callable) -> subprocess.CompletedProcess:
    cmd = ["git", "-C", str(repo), *args]
    return runner(cmd, capture_output=True, text=True, check=False)


def list_local_branches(
    repo_path: str | Path,
    runner: callable = subprocess.run,
) -> BranchListResult:
    repo = Path(repo_path)
    logger.debug("Listing local branches repo=%s", repo)

    inside = _run_git(repo, ["rev-parse", "--is-inside-work-tree"], runner)
    if inside.returncode != 0:
        logger.error("Repository is not accessible repo=%s", repo)
        raise BranchNexusError(
            f"Repository is not accessible: {repo}",
            code=ExitCode.GIT_ERROR,
            hint="Check the path and ensure it is a valid Git repository.",
        )

    detached = _run_git(repo, ["symbolic-ref", "--short", "-q", "HEAD"], runner)
    warning = ""
    if detached.returncode != 0:
        warning = "Detached HEAD detected. Branch operations may be limited."
        logger.warning("Detached HEAD detected repo=%s", repo)

    listing = _run_git(repo, ["branch", "--format=%(refname:short)"], runner)
    if listing.returncode != 0:
        logger.error("Failed to list local branches repo=%s stderr=%s", repo, listing.stderr.strip())
        raise BranchNexusError(
            f"Failed to list local branches for {repo}",
            code=ExitCode.GIT_ERROR,
            hint="Run `git branch` manually to inspect repository state.",
        )

    branches = sorted({line.strip() for line in listing.stdout.splitlines() if line.strip()})
    if not branches:
        logger.error("No local branches found repo=%s", repo)
        raise BranchNexusError(
            "No local branches found.",
            code=ExitCode.GIT_ERROR,
            hint="Create an initial commit and at least one branch.",
        )

    logger.debug("Discovered %s local branches repo=%s", len(branches), repo)
    return BranchListResult(branches=branches, warning=warning)
