from __future__ import annotations

from pathlib import Path

import pytest

_SECURITY_TEST_FILES = {
    "test_github_repositories.py",
    "test_remote_workspace.py",
    "test_wsl_discovery.py",
}


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    for item in items:
        path = Path(str(getattr(item, "path", item.fspath)))
        name = path.name

        if "integration" in path.parts:
            item.add_marker(pytest.mark.integration)
            item.add_marker(pytest.mark.slow)

        if name in _SECURITY_TEST_FILES:
            item.add_marker(pytest.mark.security)
