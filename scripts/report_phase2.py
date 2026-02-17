from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate Phase 2 JSON and Markdown summaries from metrics and events."
    )
    parser.add_argument("--metrics", type=Path, required=True, help="Path to metrics JSON file.")
    parser.add_argument("--events", type=Path, required=True, help="Path to events JSON file.")
    parser.add_argument(
        "--output-json",
        type=Path,
        required=True,
        help="Path to write summarized JSON payload.",
    )
    parser.add_argument(
        "--output-md",
        type=Path,
        required=True,
        help="Path to write markdown dashboard output.",
    )
    return parser.parse_args()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _top_errors(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for event in events:
        if not isinstance(event, dict):
            continue
        level = str(event.get("level", "")).strip().lower()
        if level != "error":
            continue
        reason = str(event.get("reason", "unknown")).strip() or "unknown"
        counts[reason] += 1

    return [
        {"reason": reason, "count": count}
        for reason, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _build_markdown(metrics: dict[str, Any], top_errors: list[dict[str, Any]]) -> str:
    lines = [
        "# Phase 2 Summary",
        "",
        "## Metrics",
        "",
        f"- Total runs: {metrics.get('total_runs', 0)}",
        f"- Success rate: {metrics.get('success_rate', 0)}",
        f"- Failure rate: {metrics.get('failure_rate', 0)}",
        f"- p50 (ms): {metrics.get('p50_ms', 0)}",
        f"- p95 (ms): {metrics.get('p95_ms', 0)}",
    ]

    if top_errors:
        lines.extend(["", "## Top Errors", "", "| Reason | Count |", "| --- | ---: |"])
        for item in top_errors:
            lines.append(f"| {item['reason']} | {item['count']} |")
    else:
        lines.extend(["", "## Top Errors", "", "_No error events found._"])

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()

    metrics_data = _read_json(args.metrics)
    events_data = _read_json(args.events)

    metrics = metrics_data if isinstance(metrics_data, dict) else {}
    events = events_data if isinstance(events_data, list) else []
    top_errors = _top_errors(events)

    payload = {
        "metrics": metrics,
        "top_errors": top_errors,
        "error_total": sum(item["count"] for item in top_errors),
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    args.output_md.write_text(_build_markdown(metrics, top_errors), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
