from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_report_phase2_generates_dashboard(tmp_path: Path) -> None:
    metrics = tmp_path / "metrics.json"
    metrics.write_text(
        json.dumps(
            {
                "total_runs": 10,
                "success_rate": 0.9,
                "failure_rate": 0.1,
                "p50_ms": 12,
                "p95_ms": 25,
            }
        ),
        encoding="utf-8",
    )

    events = tmp_path / "events.json"
    events.write_text(
        json.dumps(
            [
                {"level": "error", "reason": "network"},
                {"level": "error", "reason": "network"},
                {"level": "error", "reason": "auth"},
            ]
        ),
        encoding="utf-8",
    )

    out_json = tmp_path / "out.json"
    out_md = tmp_path / "out.md"

    root = Path(__file__).resolve().parents[1]
    process = subprocess.run(
        [
            sys.executable,
            str(root / "scripts" / "report_phase2.py"),
            "--metrics",
            str(metrics),
            "--events",
            str(events),
            "--output-json",
            str(out_json),
            "--output-md",
            str(out_md),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert process.returncode == 0
    payload = json.loads(out_json.read_text(encoding="utf-8"))
    assert payload["top_errors"][0]["reason"] == "network"
    assert "Phase 2 Summary" in out_md.read_text(encoding="utf-8")
