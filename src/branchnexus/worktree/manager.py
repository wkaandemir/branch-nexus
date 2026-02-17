"""Worktree lifecycle manager."""

from __future__ import annotations

import logging as py_logging
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol

from typing_extensions import TypedDict

from branchnexus.errors import BranchNexusError, ExitCode

logger = py_logging.getLogger(__name__)


_SANITIZE_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


class SubprocessRunner(Protocol):
    def __call__(
        self,
        args: list[str],
        *,
        capture_output: bool = False,
        text: bool = False,
        check: bool = False,
    ) -> subprocess.CompletedProcess[str]: ...


class WorktreeAssignmentDict(TypedDict):
    pane: int
    repo_path: str
    branch: str


@dataclass(frozen=True)
class WorktreeAssignment:
    pane: int
    repo_path: Path | PurePosixPath
    branch: str


@dataclass
class ManagedWorktree:
    pane: int
    repo_path: Path | PurePosixPath
    branch: str
    path: Path | PurePosixPath


class WorktreeManager:
    def __init__(
        self, base_dir: str | Path | PurePosixPath, cleanup_policy: str = "session"
    ) -> None:
        if type(base_dir) is PurePosixPath:
            self.base_dir: Path | PurePosixPath = base_dir
            self._posix_mode = True
        else:
            self.base_dir = Path(base_dir)
            self.base_dir.mkdir(parents=True, exist_ok=True)
            self._posix_mode = False
        self.cleanup_policy = cleanup_policy
        self._managed: list[ManagedWorktree] = []

    @staticmethod
    def _safe(value: str) -> str:
        cleaned = _SANITIZE_PATTERN.sub("-", value).strip("-")
        return cleaned or "default"

    @staticmethod
    def _as_posix(value: str | Path | PurePosixPath) -> str:
        raw = str(value).replace("\\", "/")
        while raw.startswith("//"):
            raw = raw[1:]
        return raw

    def _command_path(self, value: str | Path | PurePosixPath) -> str:
        if self._posix_mode:
            return self._as_posix(value)
        return str(value)

    def _expected_branch_ref(self, branch: str) -> str:
        if branch.startswith("refs/heads/"):
            return branch
        return f"refs/heads/{branch}"

    def _cast_path(self, value: str) -> Path | PurePosixPath:
        if self._posix_mode:
            return PurePosixPath(value)
        return Path(value)

    def _is_under_base_dir(self, path: str | Path | PurePosixPath) -> bool:
        if self._posix_mode:
            base = PurePosixPath(self._command_path(self.base_dir))
            candidate = PurePosixPath(self._command_path(path))
            return candidate == base or base in candidate.parents

        # On Windows, path normalization is critical for cross-drive or mixed-slash paths
        base_path = Path(self.base_dir).resolve()
        try:
            candidate_path = Path(path).resolve()
        except (OSError, ValueError):
            # If resolve fails (e.g. invalid path), fallback to relative_to check on raw paths
            candidate_path = Path(path)

        try:
            candidate_path.relative_to(base_path)
            return True
        except ValueError:
            return False

    def _worktree_path_for_branch(
        self,
        assignment: WorktreeAssignment,
        *,
        runner: SubprocessRunner,
    ) -> Path | PurePosixPath | None:
        result = runner(
            [
                "git",
                "-C",
                self._command_path(assignment.repo_path),
                "worktree",
                "list",
                "--porcelain",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.debug(
                "Skipping branch-in-use lookup pane=%s repo=%s due to command failure",
                assignment.pane,
                assignment.repo_path,
            )
            return None

        expected_ref = self._expected_branch_ref(assignment.branch)
        current_worktree = ""
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("worktree "):
                current_worktree = line.split(" ", 1)[1].strip()
                continue
            if line.startswith("branch ") and current_worktree:
                branch_ref = line.split(" ", 1)[1].strip()
                if branch_ref == expected_ref:
                    return self._cast_path(current_worktree)
        return None

    def _path_exists(
        self,
        path: str | Path | PurePosixPath,
        *,
        runner: SubprocessRunner,
    ) -> bool:
        if self._posix_mode:
            command = ["bash", "-lc", f"test -e {shlex.quote(self._command_path(path))}"]
            result = runner(command, capture_output=True, text=True, check=False)
            return result.returncode == 0
        return Path(path).exists()

    def _existing_worktree_branch(
        self,
        path: str | Path | PurePosixPath,
        *,
        runner: SubprocessRunner,
    ) -> str:
        result = runner(
            ["git", "-C", self._command_path(path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    def build_worktree_path(self, assignment: WorktreeAssignment) -> Path | PurePosixPath:
        repo_name = self._safe(PurePosixPath(self._as_posix(assignment.repo_path)).name)
        branch_name = self._safe(assignment.branch)
        return self.base_dir / repo_name / f"pane-{assignment.pane}-{branch_name}"

    def add_worktree(
        self,
        assignment: WorktreeAssignment,
        runner: SubprocessRunner = subprocess.run,
    ) -> ManagedWorktree:
        target = self.build_worktree_path(assignment)
        logger.debug(
            "Adding worktree pane=%s repo=%s branch=%s target=%s",
            assignment.pane,
            assignment.repo_path,
            assignment.branch,
            target,
        )

        branch_in_use_path = self._worktree_path_for_branch(assignment, runner=runner)
        if branch_in_use_path is not None:
            if self._is_under_base_dir(branch_in_use_path):
                if self._path_exists(branch_in_use_path, runner=runner):
                    logger.info(
                        "Reusing existing branch worktree pane=%s repo=%s branch=%s existing=%s",
                        assignment.pane,
                        assignment.repo_path,
                        assignment.branch,
                        branch_in_use_path,
                    )
                    managed = ManagedWorktree(
                        pane=assignment.pane,
                        repo_path=assignment.repo_path,
                        branch=assignment.branch,
                        path=branch_in_use_path,
                    )
                    self._managed.append(managed)
                    return managed
            else:
                logger.error(
                    "Branch already checked out outside managed base pane=%s branch=%s path=%s",
                    assignment.pane,
                    assignment.branch,
                    branch_in_use_path,
                )
                raise BranchNexusError(
                    f"Branch '{assignment.branch}' baska bir worktree tarafindan kullaniliyor.",
                    code=ExitCode.GIT_ERROR,
                    hint=(
                        f"Mevcut yol: {branch_in_use_path}. "
                        "Farkli branch secin veya bu worktree'i kapatip tekrar deneyin."
                    ),
                )

        if self._path_exists(target, runner=runner):
            existing_branch = self._existing_worktree_branch(target, runner=runner)
            if existing_branch == assignment.branch:
                logger.info(
                    "Reusing existing worktree pane=%s target=%s branch=%s",
                    assignment.pane,
                    target,
                    assignment.branch,
                )
                managed = ManagedWorktree(
                    pane=assignment.pane,
                    repo_path=assignment.repo_path,
                    branch=assignment.branch,
                    path=target,
                )
                self._managed.append(managed)
                return managed
            if existing_branch:
                logger.error(
                    "Existing worktree branch mismatch pane=%s target=%s expected=%s actual=%s",
                    assignment.pane,
                    target,
                    assignment.branch,
                    existing_branch,
                )
                raise BranchNexusError(
                    f"Worktree path already exists for pane {assignment.pane}",
                    code=ExitCode.GIT_ERROR,
                    hint=(
                        f"Existing branch is '{existing_branch}'. "
                        "Cleanup old worktree or select another branch."
                    ),
                )

        if self._posix_mode:
            mkdir_result = runner(
                ["mkdir", "-p", self._command_path(PurePosixPath(target).parent)],
                capture_output=True,
                text=True,
                check=False,
            )
            if mkdir_result.returncode != 0:
                logger.error(
                    "Failed to create worktree parent pane=%s stderr=%s",
                    assignment.pane,
                    mkdir_result.stderr.strip(),
                )
                raise BranchNexusError(
                    f"Failed to prepare worktree parent for pane {assignment.pane}",
                    code=ExitCode.GIT_ERROR,
                    hint=mkdir_result.stderr.strip() or "Check filesystem permissions inside WSL.",
                )
        else:
            Path(target).parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "git",
            "-C",
            self._command_path(assignment.repo_path),
            "worktree",
            "add",
            self._command_path(target),
            assignment.branch,
        ]
        result = runner(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error(
                "git worktree add failed pane=%s cmd=%s stderr=%s",
                assignment.pane,
                cmd,
                result.stderr.strip(),
            )
            raise BranchNexusError(
                f"Failed to create worktree for pane {assignment.pane}",
                code=ExitCode.GIT_ERROR,
                hint=result.stderr.strip() or "Check branch existence and repo health.",
            )

        managed = ManagedWorktree(
            pane=assignment.pane,
            repo_path=assignment.repo_path,
            branch=assignment.branch,
            path=target,
        )
        self._managed.append(managed)
        return managed

    def materialize(
        self,
        assignments: list[WorktreeAssignment],
        runner: SubprocessRunner = subprocess.run,
    ) -> list[ManagedWorktree]:
        logger.debug("Materializing %s worktree assignments", len(assignments))
        created: list[ManagedWorktree] = []
        for assignment in sorted(assignments, key=lambda item: item.pane):
            created.append(self.add_worktree(assignment, runner=runner))
        return created

    def check_dirty(
        self, worktree: ManagedWorktree, runner: SubprocessRunner = subprocess.run
    ) -> bool:
        cmd = ["git", "-C", self._command_path(worktree.path), "status", "--porcelain"]
        result = runner(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error(
                "Dirty check failed for %s stderr=%s", worktree.path, result.stderr.strip()
            )
            raise BranchNexusError(
                f"Dirty check failed for {worktree.path}",
                code=ExitCode.GIT_ERROR,
                hint=result.stderr.strip() or "Run git status manually.",
            )
        dirty = bool(result.stdout.strip())
        logger.debug("Dirty check path=%s dirty=%s", worktree.path, dirty)
        return dirty

    def cleanup(
        self,
        runner: SubprocessRunner = subprocess.run,
        *,
        force: bool = True,
        selected: list[ManagedWorktree] | None = None,
        ignore_policy: bool = False,
    ) -> list[Path | PurePosixPath]:
        if self.cleanup_policy == "persistent" and not ignore_policy:
            logger.debug("Cleanup skipped due to persistent policy")
            return []

        targets = selected or list(self._managed)
        removed: list[Path | PurePosixPath] = []
        removed_paths: set[str] = set()
        for managed in targets:
            managed_path = self._command_path(managed.path)
            if managed_path in removed_paths:
                continue
            removed_paths.add(managed_path)
            cmd = ["git", "-C", self._command_path(managed.repo_path), "worktree", "remove"]
            if force:
                cmd.append("--force")
            cmd.append(managed_path)
            result = runner(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                logger.error(
                    "Cleanup failed path=%s stderr=%s",
                    managed.path,
                    result.stderr.strip(),
                )
                raise BranchNexusError(
                    f"Cleanup failed for {managed.path}",
                    code=ExitCode.GIT_ERROR,
                    hint=result.stderr.strip() or "Resolve worktree state and retry.",
                )
            removed.append(managed.path)
            logger.debug("Removed worktree path=%s", managed.path)

        return removed

    @property
    def managed(self) -> list[ManagedWorktree]:
        return list(self._managed)
