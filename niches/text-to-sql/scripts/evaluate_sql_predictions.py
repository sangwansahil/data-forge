#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.niches.text_to_sql.eval import evaluate_prediction_records, iter_jsonl, write_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True, help="JSONL with db_id, question, gold_sql, predicted_sql")
    parser.add_argument("--database-dir", required=True)
    parser.add_argument("--out", required=True, help="Directory for report.json and per_example.jsonl")
    parser.add_argument("--ordered", action="store_true")
    args = parser.parse_args()

    records = list(iter_jsonl(Path(args.predictions)))
    results, summary = evaluate_prediction_records(
        records=records,
        database_dir=Path(args.database_dir),
        ordered=args.ordered,
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    write_jsonl(out_dir / "per_example.jsonl", [result.to_dict() for result in results])
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
