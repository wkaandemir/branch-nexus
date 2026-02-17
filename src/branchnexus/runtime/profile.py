"""Runtime profile resolver for Windows + WSL2."""

from __future__ import annotations

import platform
import shutil
from collections.abc import Callable

from branchnexus.errors import BranchNexusError, ExitCode


def resolve_runtime_profile(
    *,
    system_name: str | None = None,
    wsl_path: str | None = None,
    which: Callable[[str], str | None] | None = None,
) -> str:
    system = system_name or platform.system()
    if system != "Windows":
        raise BranchNexusError(
            "BranchNexus MVP only supports Windows 10/11 with WSL2.",
            code=ExitCode.UNSUPPORTED_PLATFORM,
            hint="Run the application on Windows or use a compatible runtime host.",
        )

    which_func = which or shutil.which
    wsl_binary = wsl_path or which_func("wsl.exe")
    if not wsl_binary:
        raise BranchNexusError(
            "wsl.exe was not found.",
            code=ExitCode.UNSUPPORTED_PLATFORM,
            hint="Install WSL2 and ensure wsl.exe is available in PATH.",
        )

    return "wsl"


def sync_runtime_profile(config: object, state: object) -> str:
    profile = "wsl"
    if hasattr(config, "runtime_profile"):
        config.runtime_profile = profile
    if hasattr(state, "runtime_profile"):
        state.runtime_profile = profile
    return profile
