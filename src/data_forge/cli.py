from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_forge.core.jsonl import iter_json_records, write_jsonl
from data_forge.niches.text_to_sql.gates import evaluate_text_to_sql_row


def _validate_text_to_sql(args: argparse.Namespace) -> int:
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

    print(
        json.dumps(
            {
                "total": len(accepted) + len(rejected),
                "accepted": len(accepted),
                "rejected": len(rejected),
            },
            indent=2,
        )
    )
    return 0 if not rejected or args.allow_rejections else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="data-forge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate-text-to-sql")
    validate.add_argument("input")
    validate.add_argument("--accepted")
    validate.add_argument("--rejected")
    validate.add_argument("--report")
    validate.add_argument("--min-score", type=int, default=85)
    validate.add_argument("--allow-rejections", action="store_true")
    validate.set_defaults(func=_validate_text_to_sql)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
