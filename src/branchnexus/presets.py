"""Layout preset persistence and retrieval."""

from __future__ import annotations

from pathlib import Path

from branchnexus.errors import BranchNexusError, ExitCode

TERMINAL_TEMPLATE_CATALOG: tuple[int, ...] = (2, 4, 6, 8, 12, 16)
TERMINAL_TEMPLATE_MIN = 2
TERMINAL_TEMPLATE_MAX = 16
TERMINAL_TEMPLATE_CUSTOM = "custom"


def terminal_template_choices() -> tuple[str, ...]:
    return tuple(str(item) for item in TERMINAL_TEMPLATE_CATALOG) + (TERMINAL_TEMPLATE_CUSTOM,)


def validate_terminal_count(value: int) -> int:
    if value < TERMINAL_TEMPLATE_MIN or value > TERMINAL_TEMPLATE_MAX:
        raise BranchNexusError(
            f"Invalid terminal count: {value}",
            code=ExitCode.VALIDATION_ERROR,
            hint=f"Use a value between {TERMINAL_TEMPLATE_MIN} and {TERMINAL_TEMPLATE_MAX}.",
        )
    return value


def resolve_terminal_template(template: str | int, *, custom_value: int | None = None) -> int:
    if isinstance(template, int):
        return validate_terminal_count(template)

    normalized = str(template).strip().lower()
    if normalized == TERMINAL_TEMPLATE_CUSTOM:
        if custom_value is None:
            raise BranchNexusError(
                "Custom template requires an explicit terminal count.",
                code=ExitCode.VALIDATION_ERROR,
                hint=f"Provide --max-terminals between {TERMINAL_TEMPLATE_MIN} and {TERMINAL_TEMPLATE_MAX}.",
            )
        return validate_terminal_count(custom_value)

    if normalized.isdigit():
        return validate_terminal_count(int(normalized))

    raise BranchNexusError(
        f"Invalid terminal template: {template}",
        code=ExitCode.VALIDATION_ERROR,
        hint=f"Use one of: {', '.join(terminal_template_choices())}.",
    )


def save_preset(
    name: str,
    *,
    layout: str,
    panes: int,
    cleanup: str,
    path: str | Path | None = None,
) -> None:
    from branchnexus.config import load_config, save_config

    validate_terminal_count(panes)
    config = load_config(path)
    config.presets[name] = {"layout": layout, "panes": panes, "cleanup": cleanup}
    save_config(config, path)


def load_presets(path: str | Path | None = None) -> dict[str, dict]:
    from branchnexus.config import load_config

    config = load_config(path)
    return dict(config.presets)


def apply_preset(name: str, path: str | Path | None = None) -> dict:
    presets = load_presets(path)
    if name not in presets:
        raise BranchNexusError(
            f"Preset not found: {name}",
            code=ExitCode.VALIDATION_ERROR,
            hint="Select an existing preset or create a new one.",
        )
    return presets[name]


def delete_preset(name: str, path: str | Path | None = None) -> None:
    from branchnexus.config import load_config, save_config

    config = load_config(path)
    config.presets.pop(name, None)
    save_config(config, path)


def rename_preset(old_name: str, new_name: str, path: str | Path | None = None) -> None:
    from branchnexus.config import load_config, save_config

    config = load_config(path)
    if old_name not in config.presets:
        raise BranchNexusError(
            f"Preset not found: {old_name}",
            code=ExitCode.VALIDATION_ERROR,
            hint="Choose an existing preset to rename.",
        )
    config.presets[new_name] = config.presets.pop(old_name)
    save_config(config, path)
