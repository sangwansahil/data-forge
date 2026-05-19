from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SqlEvalResult:
    example_id: str
    db_id: str
    question: str
    gold_sql: str
    predicted_sql: str
    exact_execution_match: bool
    gold_error: str | None = None
    prediction_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "db_id": self.db_id,
            "question": self.question,
            "gold_sql": self.gold_sql,
            "predicted_sql": self.predicted_sql,
            "exact_execution_match": self.exact_execution_match,
            "gold_error": self.gold_error,
            "prediction_error": self.prediction_error,
        }


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    for line_no, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"{path}:{line_no}: expected JSON object")
        yield payload


def write_jsonl(path: Path, records: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))


def sqlite_path(database_dir: Path, db_id: str) -> Path:
    candidates = [
        database_dir / db_id / f"{db_id}.sqlite",
        database_dir / db_id / f"{db_id}.db",
        database_dir / f"{db_id}.sqlite",
        database_dir / f"{db_id}.db",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"could not find sqlite database for db_id={db_id!r} under {database_dir}")


def introspect_schema(database_path: Path, *, sample_rows: int = 0) -> str:
    conn = sqlite3.connect(str(database_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        lines = ["Dialect: sqlite", "", "Schema:"]
        for table in tables:
            columns = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            column_sql = ", ".join(f"{column['name']} {column['type'] or 'TEXT'}" for column in columns)
            lines.append(f"CREATE TABLE {table} ({column_sql});")
            if sample_rows > 0:
                rows = conn.execute(f'SELECT * FROM "{table}" LIMIT ?', (sample_rows,)).fetchall()
                if rows:
                    lines.append(f"Sample rows for {table}:")
                    for row in rows:
                        lines.append(json.dumps(dict(row), sort_keys=True))
            lines.append("")
        return "\n".join(lines).strip()
    finally:
        conn.close()


def prompt_for_example(example: Mapping[str, Any], schema_prompt: str) -> str:
    return (
        f"{schema_prompt}\n\n"
        f"Question:\n{example['question']}\n\n"
        "Return one SQLite query. Do not include explanation."
    )


def spider_examples_to_prompt_records(
    *,
    examples: Sequence[Mapping[str, Any]],
    database_dir: Path,
    limit: int | None = None,
    sample_rows: int = 0,
) -> list[dict[str, Any]]:
    records = []
    schema_cache: dict[str, str] = {}
    selected = examples if limit is None else examples[:limit]
    for index, example in enumerate(selected):
        db_id = str(example["db_id"])
        if db_id not in schema_cache:
            schema_cache[db_id] = introspect_schema(sqlite_path(database_dir, db_id), sample_rows=sample_rows)
        gold_sql = str(example.get("query") or example.get("gold_sql") or "")
        records.append(
            {
                "example_id": str(example.get("id", index)),
                "db_id": db_id,
                "question": str(example["question"]),
                "gold_sql": gold_sql,
                "prompt": prompt_for_example(example, schema_cache[db_id]),
            }
        )
    return records


SQL_FENCE = re.compile(r"```(?:sql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
SQL_START = re.compile(r"\b(?:WITH|SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE)
SQL_STOP = re.compile(r"(?:</?think>|\n\s*(?:The|This|Explanation|Note|Let|We)\b|```)", re.IGNORECASE)


def extract_sql(text: str) -> str:
    stripped = text.strip()
    if "</think>" in stripped:
        stripped = stripped.split("</think>")[-1].strip()
    fenced = SQL_FENCE.search(stripped)
    if fenced:
        stripped = fenced.group(1).strip()
    start = SQL_START.search(stripped)
    if start:
        stripped = stripped[start.start() :].strip()
        stop = SQL_STOP.search(stripped)
        if stop and stop.start() > 0:
            stripped = stripped[: stop.start()].strip()
        statement_end = stripped.find(";")
        if statement_end >= 0:
            stripped = stripped[:statement_end].strip()
    lines = []
    for line in stripped.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned.lower().startswith(("here is", "sql:", "answer:")):
            continue
        lines.append(cleaned)
    sql = " ".join(lines).strip()
    return sql[:-1].strip() if sql.endswith(";") else sql


def _execute(database_path: Path, sql: str) -> tuple[list[tuple[Any, ...]] | None, str | None]:
    conn = sqlite3.connect(str(database_path))
    try:
        cursor = conn.execute(sql)
        return cursor.fetchall(), None
    except Exception as exc:  # noqa: BLE001 - evaluation report should preserve failure string
        return None, str(exc)
    finally:
        conn.close()


def _normalize_value(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


def normalize_result(rows: Sequence[Sequence[Any]] | None, *, ordered: bool = False) -> list[tuple[Any, ...]] | None:
    if rows is None:
        return None
    normalized = [tuple(_normalize_value(value) for value in row) for row in rows]
    return normalized if ordered else sorted(normalized, key=repr)


def evaluate_prediction_records(
    *,
    records: Sequence[Mapping[str, Any]],
    database_dir: Path,
    ordered: bool = False,
) -> tuple[list[SqlEvalResult], dict[str, Any]]:
    results = []
    for index, record in enumerate(records):
        db_id = str(record["db_id"])
        database_path = sqlite_path(database_dir, db_id)
        gold_sql = str(record.get("gold_sql") or record.get("query") or "")
        predicted_sql = extract_sql(str(record.get("predicted_sql") or record.get("prediction") or ""))
        gold_rows, gold_error = _execute(database_path, gold_sql)
        predicted_rows, prediction_error = _execute(database_path, predicted_sql) if predicted_sql else (None, "empty prediction")
        match = (
            gold_error is None
            and prediction_error is None
            and normalize_result(gold_rows, ordered=ordered) == normalize_result(predicted_rows, ordered=ordered)
        )
        results.append(
            SqlEvalResult(
                example_id=str(record.get("example_id", index)),
                db_id=db_id,
                question=str(record.get("question", "")),
                gold_sql=gold_sql,
                predicted_sql=predicted_sql,
                exact_execution_match=match,
                gold_error=gold_error,
                prediction_error=prediction_error,
            )
        )
    summary = summarize_eval_results(results)
    return results, summary


def summarize_eval_results(results: Sequence[SqlEvalResult]) -> dict[str, Any]:
    total = len(results)
    correct = sum(1 for result in results if result.exact_execution_match)
    by_db: Counter[str] = Counter()
    correct_by_db: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    for result in results:
        by_db[result.db_id] += 1
        if result.exact_execution_match:
            correct_by_db[result.db_id] += 1
        elif result.prediction_error:
            errors[result.prediction_error] += 1
    return {
        "total": total,
        "correct": correct,
        "execution_accuracy": round(correct / total, 4) if total else 0.0,
        "by_db": {
            db_id: {
                "total": count,
                "correct": correct_by_db[db_id],
                "execution_accuracy": round(correct_by_db[db_id] / count, 4),
            }
            for db_id, count in sorted(by_db.items())
        },
        "top_prediction_errors": dict(errors.most_common(20)),
    }
