#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import time
from pathlib import Path
from typing import Any


def _load_progress(run_dir: Path, target: int) -> dict[str, Any]:
    reports = list((run_dir / "shards").glob("*/reports/*_validation_report.json"))
    raw = accepted = rejected = 0
    reasons: dict[str, int] = {}
    shards: dict[str, dict[str, int]] = {}
    for path in reports:
        report = json.loads(path.read_text())
        raw += int(report.get("raw_count", 0))
        accepted += int(report.get("accepted_count", 0))
        rejected += int(report.get("rejected_count", 0))
        shard = path.parts[-3]
        shard_summary = shards.setdefault(shard, {"raw": 0, "accepted": 0, "rejected": 0, "reports": 0})
        shard_summary["raw"] += int(report.get("raw_count", 0))
        shard_summary["accepted"] += int(report.get("accepted_count", 0))
        shard_summary["rejected"] += int(report.get("rejected_count", 0))
        shard_summary["reports"] += 1
        for reason, count in report.get("top_rejection_reasons", {}).items():
            reasons[str(reason)] = reasons.get(str(reason), 0) + int(count)
    return {
        "target": target,
        "reports": len(reports),
        "raw": raw,
        "accepted": accepted,
        "rejected": rejected,
        "acceptance_rate": round(accepted / max(raw, 1), 4),
        "progress_pct": round(accepted / max(target, 1) * 100, 2),
        "top_reasons": dict(sorted(reasons.items(), key=lambda item: -item[1])[:8]),
        "shards": dict(sorted(shards.items())),
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def _bar(accepted: int, target: int, width: int = 40) -> str:
    filled = min(width, int(width * accepted / max(target, 1)))
    return "[" + "#" * filled + "." * (width - filled) + f"] {accepted}/{target}"


def _write_html(path: Path, progress: dict[str, Any], refresh_seconds: int) -> None:
    pct = min(100.0, float(progress["progress_pct"]))
    reasons = "\n".join(
        f"<tr><td>{html.escape(reason)}</td><td>{count}</td></tr>"
        for reason, count in progress["top_reasons"].items()
    )
    shards = "\n".join(
        "<tr>"
        f"<td>{html.escape(name)}</td>"
        f"<td>{summary['accepted']}</td>"
        f"<td>{summary['raw']}</td>"
        f"<td>{summary['rejected']}</td>"
        f"<td>{summary['reports']}</td>"
        "</tr>"
        for name, summary in progress["shards"].items()
    )
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="{refresh_seconds}">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>data-forge progress</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #17202a; }}
    .wrap {{ max-width: 980px; margin: 0 auto; }}
    .bar {{ width: 100%; height: 28px; border: 1px solid #9aa6b2; background: #f2f4f7; }}
    .fill {{ height: 100%; width: {pct:.2f}%; background: #1f7a4d; }}
    .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin: 24px 0; }}
    .metric {{ border: 1px solid #d7dde4; padding: 12px; }}
    .label {{ color: #667085; font-size: 12px; text-transform: uppercase; }}
    .value {{ font-size: 24px; font-weight: 700; margin-top: 4px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e4e7ec; padding: 8px; font-size: 14px; }}
    code {{ background: #f2f4f7; padding: 2px 4px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>data-forge generation progress</h1>
    <p><code>{progress['accepted']}/{progress['target']}</code> accepted rows. Updated {html.escape(progress['updated_at'])}. Auto-refreshes every {refresh_seconds}s.</p>
    <div class="bar"><div class="fill"></div></div>
    <div class="metrics">
      <div class="metric"><div class="label">Progress</div><div class="value">{progress['progress_pct']}%</div></div>
      <div class="metric"><div class="label">Accepted</div><div class="value">{progress['accepted']}</div></div>
      <div class="metric"><div class="label">Raw</div><div class="value">{progress['raw']}</div></div>
      <div class="metric"><div class="label">Acceptance</div><div class="value">{progress['acceptance_rate']:.1%}</div></div>
    </div>
    <h2>Top Rejection Reasons</h2>
    <table><thead><tr><th>Reason</th><th>Count</th></tr></thead><tbody>{reasons}</tbody></table>
    <h2>Shards</h2>
    <table><thead><tr><th>Shard</th><th>Accepted</th><th>Raw</th><th>Rejected</th><th>Batches</th></tr></thead><tbody>{shards}</tbody></table>
  </div>
</body>
</html>
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--target", type=int, default=10000)
    parser.add_argument("--out")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    out = Path(args.out) if args.out else run_dir / "progress.html"
    while True:
        progress = _load_progress(run_dir, args.target)
        print(_bar(progress["accepted"], args.target), json.dumps(progress, sort_keys=True), flush=True)
        _write_html(out, progress, refresh_seconds=args.interval)
        (run_dir / "progress.json").write_text(json.dumps(progress, indent=2, sort_keys=True) + "\n")
        if not args.watch:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
