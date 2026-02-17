from __future__ import annotations

import pytest

from branchnexus.config import AppConfig
from branchnexus.errors import BranchNexusError
from branchnexus.runtime.profile import resolve_runtime_profile, sync_runtime_profile
from branchnexus.ui.state import AppState


def test_runtime_profile_requires_windows() -> None:
    with pytest.raises(BranchNexusError):
        resolve_runtime_profile(system_name="Linux", wsl_path="/usr/bin/wsl.exe")


def test_runtime_profile_requires_wsl_binary() -> None:
    with pytest.raises(BranchNexusError):
        resolve_runtime_profile(system_name="Windows", wsl_path=None, which=lambda _: None)


def test_runtime_profile_is_deterministic_wsl() -> None:
    profile = resolve_runtime_profile(system_name="Windows", wsl_path="C:/Windows/System32/wsl.exe")
    assert profile == "wsl"


def test_sync_runtime_profile_updates_state_and_config() -> None:
    config = AppConfig(runtime_profile="other")
    state = AppState(runtime_profile="other")
    profile = sync_runtime_profile(config, state)
    assert profile == "wsl"
    assert config.runtime_profile == "wsl"
    assert state.runtime_profile == "wsl"
