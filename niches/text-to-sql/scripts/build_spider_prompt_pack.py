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

from data_forge.niches.text_to_sql.eval import spider_examples_to_prompt_records, write_jsonl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--examples", required=True, help="Spider-style JSON examples, e.g. dev.json")
    parser.add_argument("--database-dir", required=True, help="Directory containing SQLite databases")
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample-rows", type=int, default=0)
    args = parser.parse_args()

    examples = json.loads(Path(args.examples).read_text())
    if not isinstance(examples, list):
        raise SystemExit("--examples must be a JSON array")
    records = spider_examples_to_prompt_records(
        examples=examples,
        database_dir=Path(args.database_dir),
        limit=args.limit,
        sample_rows=args.sample_rows,
    )
    write_jsonl(Path(args.out), records)
    print(json.dumps({"examples": len(records), "out": args.out}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
