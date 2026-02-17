"""Runtime constants extracted from app.py."""

from __future__ import annotations

import re
from typing import Literal

# =============================================================================
# TIMEOUT CONSTANTS (in seconds)
# =============================================================================

WSL_PREFLIGHT_TIMEOUT_SECONDS: int = 300
WSL_GIT_TIMEOUT_SECONDS: int = 300
WSL_PROGRESS_LOG_IO_TIMEOUT_SECONDS: int = 15
COMMAND_HEARTBEAT_SECONDS: int = 10
WSL_GIT_PROBE_TIMEOUT_SECONDS: int = 30
WSL_FETCH_DRY_RUN_TIMEOUT_SECONDS: int = 15
WSL_GIT_CLONE_PARTIAL_TIMEOUT_SECONDS: int = 180
WSL_GIT_CLONE_FULL_TIMEOUT_SECONDS: int = 300
HOST_GIT_CLONE_TIMEOUT_SECONDS: int = 90
WSL_GH_CLONE_TIMEOUT_SECONDS: int = 240

# =============================================================================
# LIMIT CONSTANTS
# =============================================================================

TERMINAL_LOG_TRUNCATE_LIMIT: int = 320
DEFAULT_LOG_TRUNCATE_LIMIT: int = 700

# =============================================================================
# PATH CONSTANTS
# =============================================================================

DEFAULT_WSL_PROGRESS_LOG_PATH: str = "/tmp/branchnexus-open-progress.log"  # nosec B108
RUNTIME_STATE_DIR: str = ".bnx"
RUNTIME_WORKTREE_DIR: str = "w"

# =============================================================================
# REGEX PATTERNS (compiled at module level)
# =============================================================================

AUTH_BEARER_PATTERN: re.Pattern[str] = re.compile(
    r"(Authorization:\s*Bearer)\s+\S+",
    re.IGNORECASE,
)

URL_CREDENTIAL_PATTERN: re.Pattern[str] = re.compile(
    r"(https?://)([^/\s:@]+):([^@\s]+)@",
)

GH_TOKEN_PATTERN: re.Pattern[str] = re.compile(
    r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b",
)

GITHUB_HTTPS_REPO_PATTERN: re.Pattern[str] = re.compile(
    r"^https?://github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)

GITHUB_SSH_REPO_PATTERN: re.Pattern[str] = re.compile(
    r"^git@github\.com:([^/\s]+)/([^/\s]+?)(?:\.git)?$",
    re.IGNORECASE,
)

# =============================================================================
# UI CONSTANTS
# =============================================================================

DEFAULT_SESSION_NAME: str = "branchnexus-runtime"
MIN_TERMINAL_COUNT: int = 2
MAX_TERMINAL_COUNT: int = 16
DEFAULT_PANE_COUNT: int = 4

# =============================================================================
# LAYOUT CONSTANTS
# =============================================================================

VALID_LAYOUTS: set[str] = {"horizontal", "vertical", "grid", "tiled"}
VALID_CLEANUP_POLICIES: set[str] = {"session", "persistent"}
VALID_TERMINAL_RUNTIMES: set[str] = {"wsl", "powershell"}

# =============================================================================
# TYPE ALIASES
# =============================================================================

LayoutType = Literal["horizontal", "vertical", "grid", "tiled"]
CleanupPolicyType = Literal["session", "persistent"]
TerminalRuntimeType = Literal["wsl", "powershell"]
