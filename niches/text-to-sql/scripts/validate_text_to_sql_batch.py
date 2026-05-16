#!/usr/bin/env python3
from __future__ import annotations

import sys
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.core.jsonl import iter_json_records, write_jsonl  # noqa: E402
from data_forge.niches.text_to_sql.gates import evaluate_text_to_sql_row  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--accepted")
    parser.add_argument("--rejected")
    parser.add_argument("--report")
    parser.add_argument("--min-score", type=int, default=85)
    parser.add_argument("--allow-rejections", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    accepted = []
    rejected = []

    for row in iter_json_records(input_path):
        result = evaluate_text_to_sql_row(row, min_score=args.min_score)
        payload = dict(row)
        payload["judge"] = result.to_dict()
        if result.accepted:
            accepted.append(payload)
        else:
            rejected.append(payload)

    if args.accepted:
        write_jsonl(Path(args.accepted), accepted)
    if args.rejected:
        write_jsonl(Path(args.rejected), rejected)
    if args.report:
        report = {
            "input": str(input_path),
            "total": len(accepted) + len(rejected),
            "accepted": len(accepted),
            "rejected": len(rejected),
            "min_score": args.min_score,
            "acceptance_rate": len(accepted) / max(1, len(accepted) + len(rejected)),
        }
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n")

    print(json.dumps({"total": len(accepted) + len(rejected), "accepted": len(accepted), "rejected": len(rejected)}, indent=2))
    return 0 if not rejected or args.allow_rejections else 1


if __name__ == "__main__":
    raise SystemExit(main())
