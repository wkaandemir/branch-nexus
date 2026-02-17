"""Remote branch fetch/list provider with degrade mode."""

from __future__ import annotations

import logging as py_logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.git.branch_provider import list_local_branches

logger = py_logging.getLogger(__name__)


@dataclass
class CombinedBranchSet:
    local: list[str]
    remote: list[str]
    warning: str = ""


def _run_git(repo: Path, args: list[str], runner: callable) -> subprocess.CompletedProcess:
    return runner(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def _normalize_remote_branches(raw: str) -> list[str]:
    result: set[str] = set()
    for line in raw.splitlines():
        entry = line.strip()
        if not entry or "->" in entry:
            continue
        result.add(entry)
    return sorted(result)


def fetch_and_list(
    repo_path: str | Path,
    runner: callable = subprocess.run,
) -> CombinedBranchSet:
    repo = Path(repo_path)
    logger.debug("Fetching and listing branches repo=%s", repo)
    local = list_local_branches(repo, runner=runner).branches

    fetch_result = _run_git(repo, ["fetch", "--prune"], runner)
    warning = ""
    if fetch_result.returncode != 0:
        logger.warning("Remote fetch failed repo=%s stderr=%s", repo, fetch_result.stderr.strip())
        warning = "Remote fetch failed; showing local branches only."
        return CombinedBranchSet(local=local, remote=[], warning=warning)

    remote_result = _run_git(repo, ["branch", "-r", "--format=%(refname:short)"], runner)
    if remote_result.returncode != 0:
        logger.error("Failed to list remote branches repo=%s stderr=%s", repo, remote_result.stderr.strip())
        raise BranchNexusError(
            "Failed to list remote branches.",
            code=ExitCode.GIT_ERROR,
            hint=(remote_result.stderr or "Check remote configuration.").strip(),
        )

    remote = _normalize_remote_branches(remote_result.stdout)
    logger.debug("Discovered %s remote branches repo=%s", len(remote), repo)
    return CombinedBranchSet(local=local, remote=remote, warning=warning)
