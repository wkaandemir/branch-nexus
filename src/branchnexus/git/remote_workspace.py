"""Remote repository sync and branch discovery in selected WSL distro."""

from __future__ import annotations

import logging as py_logging
import re
import shlex
import subprocess
from pathlib import PurePosixPath

from branchnexus.errors import BranchNexusError, ExitCode
from branchnexus.runtime.wsl_discovery import build_wsl_command

logger = py_logging.getLogger(__name__)

_REPO_NAME_FROM_URL = re.compile(r"([^/]+?)(?:\.git)?$")


def repo_name_from_url(repo_url: str) -> str:
    cleaned = repo_url.strip().rstrip("/")
    match = _REPO_NAME_FROM_URL.search(cleaned)
    if not match:
        raise BranchNexusError(
            f"Invalid repository URL: {repo_url}",
            code=ExitCode.VALIDATION_ERROR,
            hint="Provide a valid git remote URL.",
        )
    return match.group(1)


def _run_wsl(distribution: str, command: list[str], runner: callable) -> subprocess.CompletedProcess:
    return runner(
        build_wsl_command(distribution, command),
        capture_output=True,
        text=True,
        check=False,
    )


def resolve_wsl_home_directory(
    *,
    distribution: str,
    runner: callable = subprocess.run,
) -> PurePosixPath:
    result = _run_wsl(
        distribution,
        ["bash", "-lc", 'printf "%s" "$HOME"'],
        runner,
    )
    home = result.stdout.strip()
    if result.returncode != 0 or not home or not home.startswith("/"):
        logger.error(
            "Failed to resolve WSL home directory distribution=%s stderr=%s",
            distribution,
            result.stderr.strip(),
        )
        raise BranchNexusError(
            "WSL ana dizini cozulmedi.",
            code=ExitCode.RUNTIME_ERROR,
            hint=result.stderr.strip() or "WSL dagitimini acip tekrar deneyin.",
        )
    logger.debug("Resolved WSL home directory distribution=%s home=%s", distribution, home)
    return PurePosixPath(home)


def ensure_remote_repo_synced(
    *,
    distribution: str,
    repo_url: str,
    workspace_root_wsl: str,
    runner: callable = subprocess.run,
) -> PurePosixPath:
    if not repo_url.strip():
        logger.error("Remote repository URL was empty")
        raise BranchNexusError(
            "Repository URL is required.",
            code=ExitCode.VALIDATION_ERROR,
            hint="Enter a remote repository URL before continuing.",
        )

    root = PurePosixPath(workspace_root_wsl)
    repo_name = repo_name_from_url(repo_url)
    repo_path = root / repo_name
    logger.debug(
        "Ensuring remote repository sync distribution=%s repo=%s target=%s",
        distribution,
        repo_url,
        repo_path,
    )

    check_exists = _run_wsl(
        distribution,
        ["bash", "-lc", f"test -d '{repo_path}/.git'"],
        runner,
    )

    if check_exists.returncode != 0:
        logger.debug("Repository missing in workspace, cloning target=%s", repo_path)
        prepare = _run_wsl(
            distribution,
            ["mkdir", "-p", str(root)],
            runner,
        )
        if prepare.returncode != 0:
            logger.error("Failed to prepare workspace root=%s stderr=%s", root, prepare.stderr.strip())
            raise BranchNexusError(
                f"Failed to prepare workspace root: {root}",
                code=ExitCode.RUNTIME_ERROR,
                hint=prepare.stderr.strip() or "Check directory permissions inside WSL.",
            )

        clone = _run_wsl(
            distribution,
            ["git", "clone", repo_url, str(repo_path)],
            runner,
        )
        if clone.returncode != 0:
            logger.error("Failed to clone repo=%s stderr=%s", repo_url, clone.stderr.strip())
            raise BranchNexusError(
                f"Failed to clone remote repository: {repo_url}",
                code=ExitCode.GIT_ERROR,
                hint=clone.stderr.strip() or "Check repository access and credentials.",
            )
    else:
        logger.debug("Repository exists in workspace, fetching target=%s", repo_path)
        fetch = _run_wsl(
            distribution,
            ["git", "-C", str(repo_path), "fetch", "--prune", "--tags"],
            runner,
        )
        if fetch.returncode != 0:
            logger.error("Failed to fetch repo=%s stderr=%s", repo_path, fetch.stderr.strip())
            raise BranchNexusError(
                f"Failed to pull/fetch repository in WSL: {repo_path}",
                code=ExitCode.GIT_ERROR,
                hint=fetch.stderr.strip() or "Check remote access and WSL git credentials.",
            )

    # Keep the anchor repo detached so selected branches are free for worktrees.
    detach = _run_wsl(
        distribution,
        ["git", "-C", str(repo_path), "checkout", "--detach"],
        runner,
    )
    if detach.returncode != 0:
        logger.error("Failed to detach anchor repo=%s stderr=%s", repo_path, detach.stderr.strip())
        raise BranchNexusError(
            f"Failed to prepare anchor repository for worktrees: {repo_path}",
            code=ExitCode.GIT_ERROR,
            hint=detach.stderr.strip() or "Check repository state in WSL and retry.",
        )

    logger.debug("Remote repository is ready for worktree orchestration target=%s", repo_path)
    return repo_path


def list_remote_branches_in_repo(
    *,
    distribution: str,
    repo_path_wsl: str | PurePosixPath,
    runner: callable = subprocess.run,
) -> list[str]:
    logger.debug("Listing remote branches distribution=%s repo=%s", distribution, repo_path_wsl)
    command = (
        f"git -C {shlex.quote(str(repo_path_wsl))} "
        "for-each-ref --format='%(refname:short)' refs/remotes/origin"
    )
    result = _run_wsl(
        distribution,
        ["bash", "-lc", command],
        runner,
    )
    if result.returncode != 0:
        logger.error("Failed to list remote branches repo=%s stderr=%s", repo_path_wsl, result.stderr.strip())
        raise BranchNexusError(
            f"Failed to list remote branches for {repo_path_wsl}",
            code=ExitCode.GIT_ERROR,
            hint=result.stderr.strip() or "Run git fetch in WSL and retry.",
        )

    branches = sorted(
        {
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip() and "->" not in line
        }
    )
    if not branches:
        logger.error("No remote branches found repo=%s", repo_path_wsl)
        raise BranchNexusError(
            "No remote branches were found.",
            code=ExitCode.GIT_ERROR,
            hint="Ensure the remote repository has at least one branch.",
        )
    logger.debug("Discovered %s remote branches repo=%s", len(branches), repo_path_wsl)
    return branches


def list_workspace_repositories(
    *,
    distribution: str,
    workspace_root_wsl: str | PurePosixPath,
    runner: callable = subprocess.run,
) -> list[PurePosixPath]:
    root = PurePosixPath(workspace_root_wsl)
    command = (
        "find "
        f"{shlex.quote(str(root))} "
        "-mindepth 1 -maxdepth 4 -type d -name .git -print"
    )
    result = _run_wsl(
        distribution,
        ["bash", "-lc", command],
        runner,
    )
    if result.returncode != 0:
        logger.error(
            "Failed to discover local repositories root=%s stderr=%s",
            root,
            result.stderr.strip(),
        )
        raise BranchNexusError(
            f"WSL icindeki local repository listesi alinamadi: {root}",
            code=ExitCode.GIT_ERROR,
            hint=result.stderr.strip() or "Root dizin izinlerini ve yolunu kontrol edin.",
        )

    repositories = sorted(
        {
            PurePosixPath(line.strip()).parent
            for line in result.stdout.splitlines()
            if line.strip()
        }
    )
    logger.debug("Discovered %s local repositories under root=%s", len(repositories), root)
    return repositories
