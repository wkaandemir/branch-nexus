from __future__ import annotations

import subprocess

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.runtime.profile import resolve_runtime_profile
from branchnexus.runtime.wsl_discovery import list_distributions


def _cp(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def test_windows_runtime_validation_passes_with_wsl_binary() -> None:
    assert (
        resolve_runtime_profile(
            system_name="Windows",
            wsl_path="C:/Windows/System32/wsl.exe",
            which=lambda _: None,
        )
        == "wsl"
    )


def test_non_windows_runtime_validation_fails() -> None:
    with pytest.raises(BranchNexusError):
        resolve_runtime_profile(system_name="Linux", which=lambda _: "/usr/bin/wsl.exe")


def test_distribution_discovery_failure() -> None:
    with pytest.raises(BranchNexusError):
        list_distributions(runner=lambda *args, **kwargs: _cp(1, stderr="failed"))
