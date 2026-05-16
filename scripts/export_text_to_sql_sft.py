#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.core.jsonl import iter_json_records  # noqa: E402
from data_forge.niches.text_to_sql.export import row_to_sft_record  # noqa: E402
from data_forge.niches.text_to_sql.gates import evaluate_text_to_sql_row  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("--out", required=True)
    parser.add_argument("--min-score", type=int, default=85)
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with out_path.open("w") as handle:
        for row in iter_json_records(input_path):
            if not args.skip_validation:
                result = evaluate_text_to_sql_row(row, min_score=args.min_score)
                if not result.accepted:
                    raise SystemExit(f"row {row.get('id')} failed validation: {result.reasons}")
            handle.write(json.dumps(row_to_sft_record(row), sort_keys=True) + "\n")
            written += 1

    print(json.dumps({"written": written, "out": str(out_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
