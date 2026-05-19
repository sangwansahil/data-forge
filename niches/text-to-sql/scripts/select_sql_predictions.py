#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.niches.text_to_sql.eval import extract_sql, normalize_result, sqlite_path  # noqa: E402


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _execute(database_path: Path, sql: str) -> tuple[list[tuple[Any, ...]] | None, str | None]:
    if not sql:
        return None, "empty prediction"
    conn = sqlite3.connect(str(database_path))
    try:
        return conn.execute(sql).fetchall(), None
    except Exception as exc:  # noqa: BLE001 - selection report should preserve SQLite failure
        return None, str(exc)
    finally:
        conn.close()


def _record_key(record: dict[str, Any], index: int) -> tuple[str, str]:
    return str(record.get("example_id", index)), str(record["db_id"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Gold-free selector for multiple Text-to-SQL prediction files.")
    parser.add_argument("--primary", required=True, help="Preferred prediction JSONL, usually the strongest prompt variant.")
    parser.add_argument("--fallback", action="append", default=[], help="Fallback prediction JSONL. May be repeated.")
    parser.add_argument("--database-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--report", help="Optional selector report JSON path.")
    parser.add_argument(
        "--strategy",
        choices=["first-valid", "result-vote"],
        default="first-valid",
        help=(
            "first-valid chooses the first executable candidate. "
            "result-vote chooses the executable result set with the most candidate agreement, "
            "breaking ties by candidate order."
        ),
    )
    args = parser.parse_args()

    prediction_paths = [Path(args.primary), *[Path(path) for path in args.fallback]]
    prediction_sets = [_read_jsonl(path) for path in prediction_paths]
    if len({len(rows) for rows in prediction_sets}) != 1:
        raise SystemExit("All prediction files must have the same number of rows.")

    database_dir = Path(args.database_dir)
    selected: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()
    vote_size_counts: Counter[int] = Counter()

    for index, candidates in enumerate(zip(*prediction_sets, strict=True)):
        keys = [_record_key(candidate, index) for candidate in candidates]
        if len(set(keys)) != 1:
            raise SystemExit(f"Prediction files are not aligned at row {index}: {keys}")

        db_id = str(candidates[0]["db_id"])
        database_path = sqlite_path(database_dir, db_id)
        executed_candidates = []
        for candidate_index, candidate in enumerate(candidates):
            sql = extract_sql(str(candidate.get("predicted_sql") or candidate.get("prediction") or ""))
            rows, error = _execute(database_path, sql)
            executed_candidates.append((candidate_index, candidate, sql, rows, error))
            if error is not None:
                error_counts[error] += 1

        valid_candidates = [candidate for candidate in executed_candidates if candidate[4] is None]
        if args.strategy == "result-vote" and valid_candidates:
            groups: defaultdict[str, list[tuple[int, dict[str, Any], str, list[tuple[Any, ...]] | None, str | None]]] = (
                defaultdict(list)
            )
            for candidate in valid_candidates:
                groups[repr(normalize_result(candidate[3]))].append(candidate)
            chosen_group = max(groups.values(), key=lambda group: (len(group), -min(candidate[0] for candidate in group)))
            chosen_index, chosen_record, chosen_sql, _, _ = min(chosen_group, key=lambda candidate: candidate[0])
            chosen_reason = (
                "primary_result_vote"
                if chosen_index == 0
                else f"fallback_{chosen_index}_result_vote"
            )
            vote_size_counts[len(chosen_group)] += 1
        elif valid_candidates:
            chosen_index, chosen_record, chosen_sql, _, _ = valid_candidates[0]
            chosen_reason = "primary_valid" if chosen_index == 0 else f"fallback_{chosen_index}_valid"
            vote_size_counts[1] += 1
        else:
            chosen_index, chosen_record, chosen_sql, _, _ = executed_candidates[0]
            chosen_reason = "all_invalid_primary_kept"
            vote_size_counts[0] += 1

        payload = dict(chosen_record)
        payload["predicted_sql"] = chosen_sql
        payload["selector_reason"] = chosen_reason
        selected.append(payload)
        reason_counts[chosen_reason] += 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as handle:
        for record in selected:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    report = {
        "primary": str(args.primary),
        "fallback": args.fallback,
        "out": str(args.out),
        "strategy": args.strategy,
        "total": len(selected),
        "selection_reasons": dict(reason_counts),
        "vote_sizes": dict(vote_size_counts),
        "top_candidate_errors": dict(error_counts.most_common(20)),
    }
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
