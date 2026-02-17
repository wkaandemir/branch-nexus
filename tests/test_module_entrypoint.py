from __future__ import annotations

import runpy
from pathlib import Path


def test_module_entrypoint_supports_script_execution_context() -> None:
    namespace = runpy.run_path(
        str(Path("src/branchnexus/__main__.py")),
        run_name="branchnexus_entrypoint_test",
    )
    assert callable(namespace["run"])
