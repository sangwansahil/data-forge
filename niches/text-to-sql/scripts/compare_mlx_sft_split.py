#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.niches.text_to_sql.eval import extract_sql as base_extract_sql  # noqa: E402


CREATE_TABLE_RE = re.compile(r"CREATE\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)\s*\((.*?)\);", re.IGNORECASE | re.DOTALL)
SQL_START_RE = re.compile(r"\b(?:WITH|SELECT|INSERT|UPDATE|DELETE)\b.*", re.IGNORECASE | re.DOTALL)


def _load_mlx():
    try:
        from mlx_lm import generate, load
    except ImportError as exc:
        raise SystemExit("Missing MLX dependencies. Install with: python3 -m pip install -e '.[mlx]'") from exc
    return load, generate


def _iter_jsonl(path: Path):
    for line in path.read_text().splitlines():
        if line.strip():
            yield json.loads(line)


def _assistant_gold(record: dict[str, Any]) -> str:
    return str(record["messages"][-1]["content"]).strip()


def _prompt_messages(record: dict[str, Any]) -> list[dict[str, str]]:
    return [{"role": item["role"], "content": item["content"]} for item in record["messages"][:-1]]


def _user_prompt(record: dict[str, Any]) -> str:
    for message in record["messages"]:
        if message["role"] == "user":
            return str(message["content"])
    return ""


def _extract_sql(text: str) -> str:
    sql = base_extract_sql(text)
    if SQL_START_RE.match(sql.strip()):
        return sql
    match = SQL_START_RE.search(sql)
    return match.group(0).strip() if match else sql


def _normalize_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", _extract_sql(sql)).strip().rstrip(";").lower()


def _make_db(prompt: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for table, body in CREATE_TABLE_RE.findall(prompt):
        conn.execute(f"CREATE TABLE {table} ({body});")

    current_table = None
    for raw_line in prompt.splitlines():
        line = raw_line.strip()
        if line.startswith("Sample rows for ") and line.endswith(":"):
            current_table = line.removeprefix("Sample rows for ").removesuffix(":").strip()
            continue
        if not current_table:
            continue
        if not line.startswith("{"):
            current_table = None
            continue
        row = json.loads(line)
        columns = list(row.keys())
        placeholders = ", ".join("?" for _ in columns)
        quoted = ", ".join(f'"{column}"' for column in columns)
        conn.execute(
            f'INSERT INTO "{current_table}" ({quoted}) VALUES ({placeholders})',
            [row[column] for column in columns],
        )
    return conn


def _execute(conn: sqlite3.Connection, sql: str) -> tuple[list[tuple[Any, ...]] | None, str | None]:
    try:
        rows = conn.execute(_extract_sql(sql)).fetchall()
        return [tuple(row) for row in rows], None
    except Exception as exc:  # noqa: BLE001 - report exact failure
        return None, str(exc)


def _norm_result(rows: list[tuple[Any, ...]] | None) -> list[tuple[Any, ...]] | None:
    if rows is None:
        return None
    normalized = []
    for row in rows:
        normalized.append(tuple(round(value, 6) if isinstance(value, float) else value for value in row))
    return sorted(normalized, key=repr)


def _load_model(model_name: str, adapter: str | None):
    load, generate = _load_mlx()
    model, tokenizer = load(model_name, adapter_path=adapter)
    return generate, model, tokenizer


def _chat_prompt(tokenizer, record: dict[str, Any]) -> str:
    try:
        return tokenizer.apply_chat_template(
            _prompt_messages(record),
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )
    except TypeError:
        return tokenizer.apply_chat_template(_prompt_messages(record), tokenize=False, add_generation_prompt=True)


def _predict(generate, model, tokenizer, record: dict[str, Any], max_tokens: int, temp: float) -> tuple[str, float]:
    start = time.time()
    prediction = generate(
        model,
        tokenizer,
        prompt=_chat_prompt(tokenizer, record),
        max_tokens=max_tokens,
        temp=temp,
        verbose=False,
    ).strip()
    return prediction, time.time() - start


def _score(records: list[dict[str, Any]], predictions: list[dict[str, Any]]) -> dict[str, Any]:
    correct = 0
    exact = 0
    valid = 0
    errors: Counter[str] = Counter()
    per_example = []
    for record, prediction_record in zip(records, predictions, strict=True):
        conn = _make_db(_user_prompt(record))
        gold_sql = _assistant_gold(record)
        predicted_sql = _extract_sql(prediction_record["prediction"])
        gold_rows, gold_error = _execute(conn, gold_sql)
        pred_rows, pred_error = _execute(conn, predicted_sql) if predicted_sql else (None, "empty prediction")
        if pred_error is None:
            valid += 1
        else:
            errors[pred_error] += 1
        is_correct = gold_error is None and pred_error is None and _norm_result(gold_rows) == _norm_result(pred_rows)
        is_exact = _normalize_sql(gold_sql) == _normalize_sql(predicted_sql)
        correct += int(is_correct)
        exact += int(is_exact)
        per_example.append(
            {
                "source_id": record.get("metadata", {}).get("source_id"),
                "difficulty": record.get("metadata", {}).get("difficulty"),
                "domain": record.get("metadata", {}).get("domain"),
                "gold_sql": gold_sql,
                "predicted_sql": predicted_sql,
                "execution_match": is_correct,
                "exact_sql_match": is_exact,
                "prediction_error": pred_error,
            }
        )
        conn.close()

    total = len(records)
    return {
        "summary": {
            "total": total,
            "execution_accuracy": round(correct / total, 4) if total else 0.0,
            "exact_sql_match": round(exact / total, 4) if total else 0.0,
            "valid_sql_rate": round(valid / total, 4) if total else 0.0,
            "correct": correct,
            "exact": exact,
            "valid": valid,
            "top_prediction_errors": dict(errors.most_common(10)),
        },
        "per_example": per_example,
    }


def _run_label(label: str, records: list[dict[str, Any]], args, adapter: str | None) -> dict[str, Any]:
    generate, model, tokenizer = _load_model(args.model, adapter)
    predictions = []
    start = time.time()
    for index, record in enumerate(records, start=1):
        prediction, elapsed = _predict(generate, model, tokenizer, record, args.max_tokens, args.temperature)
        predictions.append({"index": index, "prediction": prediction, "latency_seconds": round(elapsed, 4)})
        print(json.dumps({"label": label, "index": index, "total": len(records), "latency_seconds": round(elapsed, 2)}), flush=True)
    scored = _score(records, predictions)
    scored["summary"]["label"] = label
    scored["summary"]["elapsed_seconds"] = round(time.time() - start, 2)
    scored["summary"]["mean_latency_seconds"] = (
        round(sum(item["latency_seconds"] for item in predictions) / len(predictions), 4) if predictions else None
    )
    return {"predictions": predictions, **scored}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--temperature", type=float, default=0.0)
    args = parser.parse_args()

    records = list(_iter_jsonl(Path(args.input)))
    if args.limit is not None:
        records = records[: args.limit]

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    base = _run_label("base", records, args, adapter=None)
    tuned = _run_label("fine_tuned", records, args, adapter=args.adapter)
    report = {
        "model": args.model,
        "adapter": args.adapter,
        "input": args.input,
        "base": base["summary"],
        "fine_tuned": tuned["summary"],
        "delta": {
            "execution_accuracy": round(tuned["summary"]["execution_accuracy"] - base["summary"]["execution_accuracy"], 4),
            "exact_sql_match": round(tuned["summary"]["exact_sql_match"] - base["summary"]["exact_sql_match"], 4),
            "valid_sql_rate": round(tuned["summary"]["valid_sql_rate"] - base["summary"]["valid_sql_rate"], 4),
        },
    }
    (out_dir / "base_predictions.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in base["per_example"])
    )
    (out_dir / "fine_tuned_predictions.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in tuned["per_example"])
    )
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
