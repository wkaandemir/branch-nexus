"""Public CLI contract and entrypoint."""

from __future__ import annotations

import argparse
import logging as py_logging
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from .errors import BranchNexusError, ExitCode, user_facing_error
from .logging import configure_logging, default_log_path
from .presets import resolve_terminal_template, terminal_template_choices, validate_terminal_count

_VALID_LAYOUTS = ("horizontal", "vertical", "grid")
_VALID_CLEANUP = ("session", "persistent")
_VALID_LOG_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")
_VALID_TERMINAL_TEMPLATES = terminal_template_choices()


def _panes_type(value: str) -> int:
    try:
        panes = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--panes must be an integer") from exc
    if panes < 2 or panes > 6:
        raise argparse.ArgumentTypeError("--panes must be between 2 and 6")
    return panes


def _log_level_type(value: str) -> str:
    normalized = value.upper()
    if normalized == "WARNING":
        normalized = "WARN"
    if normalized not in _VALID_LOG_LEVELS:
        accepted = ", ".join(_VALID_LOG_LEVELS)
        raise argparse.ArgumentTypeError(f"--log-level must be one of: {accepted}")
    return normalized


def _max_terminals_type(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--max-terminals must be an integer") from exc
    try:
        return validate_terminal_count(count)
    except BranchNexusError as exc:
        raise argparse.ArgumentTypeError(exc.hint or str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="branchnexus")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--layout", choices=_VALID_LAYOUTS, default="grid")
    parser.add_argument("--panes", type=_panes_type, default=4)
    parser.add_argument("--cleanup", choices=_VALID_CLEANUP, default="session")
    parser.add_argument("--terminal-template", choices=_VALID_TERMINAL_TEMPLATES, default="4")
    parser.add_argument("--max-terminals", type=_max_terminals_type, default=16)
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Reset workspace/config and launch GUI",
    )
    parser.add_argument("--log-level", type=_log_level_type, default="INFO")
    parser.add_argument("--log-file", type=Path, default=None)
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    return parser.parse_args(argv)


def launch_gui(*, fresh_start: bool = False) -> int:
    from branchnexus.ui.app import launch_app

    launch_app(fresh_start=fresh_start)
    return int(ExitCode.SUCCESS)


def resolve_terminal_count(namespace: argparse.Namespace) -> int:
    custom_value = namespace.max_terminals if namespace.terminal_template == "custom" else None
    count = resolve_terminal_template(namespace.terminal_template, custom_value=custom_value)
    if namespace.max_terminals < count:
        raise BranchNexusError(
            "Invalid terminal limits.",
            code=ExitCode.VALIDATION_ERROR,
            hint="--max-terminals cannot be lower than --terminal-template.",
        )
    return count


def validate_namespace(namespace: argparse.Namespace) -> None:
    resolve_terminal_count(namespace)


def run_cli_flow(namespace: argparse.Namespace) -> int:
    validate_namespace(namespace)
    return int(ExitCode.SUCCESS)


def main(
    argv: Sequence[str] | None = None,
    *,
    gui_launcher: Callable[[], int | None] | None = None,
) -> int:
    log_path = default_log_path()
    logger = configure_logging(log_file=log_path)
    parser = build_parser()
    try:
        namespace = parser.parse_args(argv)
    except SystemExit as exc:
        if exc.code not in (None, 0):
            logger.warning("Argument parsing failed with exit code %s", exc.code)
        return int(exc.code)

    if namespace.log_file is not None:
        log_path = namespace.log_file.expanduser()
    logger = configure_logging(level=namespace.log_level, log_file=log_path)

    raw_argv = list(argv) if argv is not None else list(sys.argv[1:])
    try:
        if namespace.fresh:
            launcher = gui_launcher or (lambda: launch_gui(fresh_start=True))
            logger.debug("Starting GUI flow with fresh start")
            result = launcher()
            if isinstance(result, int):
                return result
            return int(ExitCode.SUCCESS)

        if not raw_argv:
            launcher = gui_launcher or launch_gui
            logger.debug("Starting GUI flow")
            result = launcher()
            if isinstance(result, int):
                return result
            return int(ExitCode.SUCCESS)

        logger.debug("Starting CLI flow")
        return run_cli_flow(namespace)
    except BranchNexusError as exc:
        logger.error(
            "Handled BranchNexusError (code=%s): %s",
            int(exc.code),
            exc.message,
            exc_info=logger.isEnabledFor(py_logging.DEBUG),
        )
        print(user_facing_error(exc.message, hint=exc.hint), file=sys.stderr)
        return int(exc.code)
    except Exception:
        logger.exception("Unhandled exception in CLI entrypoint")
        try:
            hint = f"Inspect logs: {log_path}"
            print(user_facing_error("Unexpected runtime failure", hint=hint), file=sys.stderr)
        except Exception:
            pass
        return int(ExitCode.RUNTIME_ERROR)


def run(argv: Sequence[str] | None = None) -> int:
    return main(argv)
