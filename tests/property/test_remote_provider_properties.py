from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from branchnexus.git.remote_provider import _normalize_remote_branches

_LINE_CHARS = st.characters(min_codepoint=32, max_codepoint=126)


@given(st.lists(st.text(alphabet=_LINE_CHARS, min_size=0, max_size=30), min_size=0, max_size=40))
def test_normalize_remote_branches_returns_sorted_unique_non_redirect_entries(
    raw_lines: list[str],
) -> None:
    raw = "\n".join(raw_lines)

    result = _normalize_remote_branches(raw)
    expected = sorted({line.strip() for line in raw_lines if line.strip() and "->" not in line.strip()})

    assert result == expected


@given(st.lists(st.text(alphabet=_LINE_CHARS, min_size=0, max_size=20), min_size=0, max_size=20))
def test_normalize_remote_branches_is_idempotent(raw_lines: list[str]) -> None:
    raw = "\n".join(raw_lines)

    once = _normalize_remote_branches(raw)
    twice = _normalize_remote_branches("\n".join(once))

    assert twice == once
