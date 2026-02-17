from __future__ import annotations

import json
from pathlib import Path

import branchnexus.ui.services.windows_terminal as windows_terminal


def test_apply_font_size_updates_matching_profile(tmp_path: Path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(
        json.dumps(
            {
                "profiles": {
                    "list": [
                        {
                            "name": "Ubuntu-20.04",
                            "commandline": "wsl.exe -d Ubuntu-20.04",
                        }
                    ]
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    applied, detail = windows_terminal.apply_font_size(
        distribution="Ubuntu-20.04",
        font_size=18,
        settings_paths=[str(settings_path)],
        platform_name="nt",
    )
    assert applied is True
    assert str(settings_path) == detail
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    profile = payload["profiles"]["list"][0]
    assert profile["fontSize"] == 18
    assert profile["font"]["size"] == 18


def test_strip_jsonc_comments_and_fix_trailing_commas() -> None:
    raw = """
    {
      // single line
      "profiles": [ /* inline */ { "name": "Ubuntu", }, ],
    }
    """
    cleaned = windows_terminal.strip_jsonc_comments(raw)
    fixed = windows_terminal.fix_json_trailing_commas(cleaned)
    payload = json.loads(fixed)
    assert payload["profiles"][0]["name"] == "Ubuntu"
