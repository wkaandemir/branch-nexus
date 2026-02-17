"""Session module edge case tests."""

from __future__ import annotations

from branchnexus.session import parse_runtime_snapshot


def test_parse_runtime_snapshot_empty_terminals_returns_none() -> None:
    result = parse_runtime_snapshot({"terminals": []})
    assert result is None


def test_parse_runtime_snapshot_invalid_runtime_returns_none() -> None:
    result = parse_runtime_snapshot(
        {
            "terminals": [
                {
                    "terminal_id": "t1",
                    "title": "T1",
                    "runtime": "invalid_runtime",
                    "repo_path": "/r",
                    "branch": "b",
                }
            ]
        }
    )
    assert result is None


def test_parse_runtime_snapshot_min_valid_count() -> None:
    result = parse_runtime_snapshot(
        {
            "template_count": 2,
            "terminals": [
                {
                    "terminal_id": "t1",
                    "title": "T1",
                    "runtime": "wsl",
                    "repo_path": "/r",
                    "branch": "b",
                }
            ],
        }
    )
    assert result is not None
    assert result.template_count == 2


def test_parse_runtime_snapshot_max_valid_count() -> None:
    result = parse_runtime_snapshot(
        {
            "template_count": 16,
            "terminals": [
                {
                    "terminal_id": "t1",
                    "title": "T1",
                    "runtime": "wsl",
                    "repo_path": "/r",
                    "branch": "b",
                }
            ],
        }
    )
    assert result is not None
    assert result.template_count == 16


def test_parse_runtime_snapshot_invalid_count_returns_none() -> None:
    result = parse_runtime_snapshot(
        {
            "template_count": 1,
            "terminals": [
                {
                    "terminal_id": "t1",
                    "title": "T1",
                    "runtime": "wsl",
                    "repo_path": "/r",
                    "branch": "b",
                }
            ],
        }
    )
    assert result is None


def test_parse_runtime_snapshot_missing_terminal_id_returns_none() -> None:
    result = parse_runtime_snapshot(
        {"terminals": [{"title": "Terminal 1", "runtime": "wsl", "repo_path": "/r", "branch": "b"}]}
    )
    assert result is None
