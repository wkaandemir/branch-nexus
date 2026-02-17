from __future__ import annotations

import logging as py_logging
from pathlib import Path

import branchnexus.logging as bnx_logging


def test_default_log_path_is_expanded() -> None:
    path = bnx_logging.default_log_path()

    assert path.is_absolute()
    assert path.name == "branchnexus.log"


def test_warning_alias_maps_to_warning_level() -> None:
    logger = bnx_logging.configure_logging("warning")

    assert logger.level == bnx_logging.LOG_LEVELS["WARN"]


def test_unknown_log_level_falls_back_to_info() -> None:
    logger = bnx_logging.configure_logging("not-a-level")

    assert logger.level == py_logging.INFO


def test_configure_logging_resets_existing_handlers() -> None:
    logger = bnx_logging.configure_logging("INFO")
    first_handler_count = len(logger.handlers)
    assert first_handler_count == 1

    logger = bnx_logging.configure_logging("INFO")
    second_handler_count = len(logger.handlers)

    assert second_handler_count == 1


def test_configure_logging_adds_debug_file_handler(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "branchnexus.log"

    logger = bnx_logging.configure_logging("ERROR", log_file=log_file)
    file_handlers = [
        handler for handler in logger.handlers if isinstance(handler, py_logging.FileHandler)
    ]

    assert len(file_handlers) == 1
    assert file_handlers[0].level == py_logging.DEBUG
    assert log_file.exists()


def test_configure_logging_ignores_file_handler_oserror(monkeypatch, tmp_path: Path) -> None:
    def raise_os_error(*args: object, **kwargs: object) -> py_logging.Handler:
        raise OSError("disk full")

    monkeypatch.setattr(bnx_logging.py_logging, "FileHandler", raise_os_error)

    logger = bnx_logging.configure_logging("INFO", log_file=tmp_path / "nope" / "branchnexus.log")

    assert len(logger.handlers) == 1
    assert type(logger.handlers[0]) is py_logging.StreamHandler
