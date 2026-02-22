# BranchNexus - Agent Guidelines

## Project Overview

BranchNexus is a Python 3.10+ multi-branch workspace orchestrator that manages Git worktrees with tmux panel integration. It supports WSL-based development workflows on Windows.

## Build, Lint, and Test Commands

### Setup
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Testing
```bash
# Run all tests
pytest -q

# Run single test file
pytest tests/test_config.py

# Run single test function
pytest tests/test_config.py::test_load_defaults_when_config_missing

# Run with coverage
pytest --cov=src/branchnexus --cov-report=html

# Run specific test markers
pytest -m "not slow"              # Skip slow tests
pytest -m integration             # Only integration tests
pytest -m critical_regression     # Pre-merge critical tests

# Run tests in parallel
pytest -n auto
```

### Linting and Formatting
```bash
# Check code
ruff check src tests

# Auto-fix issues
ruff check --fix src tests

# Format code
ruff format src tests
```

### Type Checking
```bash
mypy src
```

### Security Analysis
```bash
bandit -r src
pip-audit
```

## Code Style Guidelines

### Imports

Always include `from __future__ import annotations` as the first import in every module. Group imports in this order, separated by blank lines:

1. Standard library (alphabetical)
2. Third-party packages (alphabetical)
3. Local imports (alphabetical)

```python
"""Module docstring."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, Field

from branchnexus.errors import BranchNexusError
```

### Type Annotations

- Use strict typing everywhere (mypy strict mode enforced)
- Prefer modern type syntax: `list[str]` over `List[str]`, `dict[str, int]` over `Dict[str, int]`
- Use `Literal` for constrained string values
- Use `TypeVar` for generic functions

```python
def process_items(items: list[str]) -> dict[str, int]:
    ...

T = TypeVar("T")

def wrap(value: T) -> list[T]:
    return [value]
```

### Naming Conventions

- **Functions/variables**: `snake_case`
- **Classes**: `PascalCase`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private module variables**: `_leading_underscore`
- **Pydantic validators**: `_validate_field_name` (classmethod with leading underscore)

### Pydantic Models

Use `ConfigDict` for model configuration and `field_validator` decorators:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

class AppConfig(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    
    default_panes: int = Field(default=4, ge=2, le=6)
    default_layout: Literal["horizontal", "vertical", "grid"] = "grid"
    
    @field_validator("default_layout")
    @classmethod
    def _validate_layout(cls, value: str) -> str:
        if value not in {"horizontal", "vertical", "grid"}:
            raise ValueError(f"Invalid layout: {value}")
        return value
```

### Error Handling

Use the structured error system with `BranchNexusError` and `ExitCode`:

```python
from branchnexus.errors import BranchNexusError, ExitCode

raise BranchNexusError(
    "Invalid WSL distribution selected.",
    code=ExitCode.RUNTIME_ERROR,
    hint="Re-open WSL selection and choose a discovered distribution.",
)
```

Use custom exception classes for retryable vs fatal errors:

```python
from branchnexus.retry import RecoverableError, FatalError

raise RecoverableError("Transient network failure")  # Will be retried
raise FatalError("Invalid configuration")            # Stops immediately
```

### Logging

Use standard `logging` module with module-level logger:

```python
import logging as py_logging

logger = py_logging.getLogger(__name__)

logger.debug("Processing items count=%s", len(items))
logger.error("Operation failed error=%s", exc)
```

Use `command_for_log()` and `sanitize_log_text()` from `branchnexus.ui.services.security` when logging potentially sensitive data.

### Line Length and Formatting

- Maximum line length: 100 characters
- Use trailing commas in multi-line collections
- Prefer parenthesized expressions over backslash line continuation

## Testing Conventions

### Test Structure

- Test files mirror source structure: `tests/test_config.py` for `src/branchnexus/config.py`
- Service tests go in `tests/ui/services/`
- Integration tests go in `tests/integration/`
- Property-based tests go in `tests/property/`

### Test Markers

Available pytest markers (defined in pyproject.toml):

- `critical_regression`: Must pass before merge
- `integration`: Cross-module integration tests
- `slow`: Extended runtime tests
- `quarantine`: Flaky tests removed from gates
- `security`: Abuse and security regression tests
- `performance`: Performance baseline tests

### Test Patterns

```python
from __future__ import annotations

from pathlib import Path

import pytest

from branchnexus.config import AppConfig, load_config


def test_load_defaults_when_config_missing(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    cfg = load_config(path)
    assert cfg.default_layout == "grid"


def test_env_overrides_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BRANCHNEXUS_GH_TOKEN", "env_token")
    # ... test implementation


@pytest.mark.integration
@pytest.mark.slow
def test_cross_module_integration() -> None:
    ...
```

## Project Structure

```
src/branchnexus/
    __init__.py         # Package exports
    cli.py              # CLI entry point
    config.py           # Configuration loading/saving
    errors.py           # Error types and exit codes
    orchestrator.py     # Main orchestration logic
    retry.py            # Retry/backoff utilities
    session.py          # Session management
    docker/             # Docker runtime support
    git/                # Git operations (branch, remote, materialize)
    hooks/              # Command hook execution
    runtime/            # WSL discovery and runtime
    terminal/           # Terminal service and PTY backend
    tmux/               # Tmux bootstrap and layouts
    ui/                 # PySide6 UI components
    worktree/           # Git worktree management
    workspace/          # VSCode workspace integration
```

## Key Patterns

### Subprocess Runner Injection

Functions that run subprocess commands accept a `runner` parameter for testability:

```python
def run_command(
    cmd: list[str],
    *,
    runner: subprocess.Run = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    return runner(cmd, capture_output=True, text=True)
```

### Configuration Access

Config is loaded from `~/.config/branchnexus/config.toml`:

```python
from branchnexus.config import load_config, save_config, AppConfig

config = load_config()
config.default_layout = "horizontal"
save_config(config)
```

### WSL Command Building

All WSL commands go through `build_wsl_command`:

```python
from branchnexus.runtime.wsl_discovery import build_wsl_command

wrapped_cmd = build_wsl_command("Ubuntu", ["git", "status"])
# Returns: ["wsl.exe", "-d", "Ubuntu", "--", "git", "status"]
```

## Pre-commit Checks

Before committing, ensure:

1. `ruff check src tests` passes
2. `pytest -q` passes (or at minimum `pytest -m "not slow"`)
3. `mypy src` passes (for typed modules not in mypy overrides)
