from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from data_forge.core.scoring import GateResult
from data_forge.niches.text_to_sql.sqlite_runner import normalize_result, run_select

REQUIRED_FIELDS = {
    "id",
    "niche",
    "domain",
    "difficulty",
    "instruction",
    "schema",
    "gold_sql",
    "expected_result",
    "verifier",
}

ALLOWED_DIFFICULTIES = {"easy", "medium", "hard", "expert"}
PLACEHOLDER_PATTERNS = re.compile(
    r"(\bfoo\b|\bbar\b|\blorem\b|\bTODO\b|\bplaceholder\b|<[^>]+>|\{[^}]+\})",
    re.IGNORECASE,
)
BENCHMARK_NAMES = re.compile(r"\b(spider|bird|livesqlbench|wikisql)\b", re.IGNORECASE)


def _stable_fingerprint(row: Mapping[str, Any]) -> str:
    payload = {
        "instruction": re.sub(r"\s+", " ", str(row.get("instruction", ""))).strip().lower(),
        "gold_sql": re.sub(r"\s+", " ", str(row.get("gold_sql", ""))).strip().lower(),
        "schema_tables": [
            table.get("name")
            for table in row.get("schema", {}).get("tables", [])
            if isinstance(table, Mapping)
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def stable_row_fingerprint(row: Mapping[str, Any]) -> str:
    return _stable_fingerprint(row)


def _compare_values(actual: Any, expected: Any, tolerance: float) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(actual) - float(expected)) <= tolerance
    return actual == expected


def _compare_results(
    actual: Sequence[Mapping[str, Any]],
    expected: Sequence[Mapping[str, Any]],
    *,
    ordered: bool,
    tolerance: float,
) -> bool:
    left = normalize_result(actual, ordered=ordered)
    right = normalize_result(expected, ordered=ordered)
    if len(left) != len(right):
        return False
    for actual_row, expected_row in zip(left, right):
        if set(actual_row) != set(expected_row):
            return False
        for key in expected_row:
            if not _compare_values(actual_row[key], expected_row[key], tolerance):
                return False
    return True


def _dimension_score(reasons: list[str], dimensions: dict[str, int]) -> int:
    score = sum(dimensions.values())
    if reasons:
        score = min(score, 84)
    return max(0, min(100, score))


def evaluate_text_to_sql_row(row: Mapping[str, Any], min_score: int = 85) -> GateResult:
    reasons: list[str] = []
    dimensions = {
        "schema_contract": 0,
        "sql_execution": 0,
        "answer_match": 0,
        "training_value": 0,
        "leakage_resistance": 0,
        "difficulty_signal": 0,
    }
    metadata: dict[str, Any] = {"fingerprint": _stable_fingerprint(row)}

    missing = sorted(REQUIRED_FIELDS - set(row))
    if missing:
        reasons.append(f"missing required fields: {', '.join(missing)}")
    else:
        dimensions["schema_contract"] = 20

    if row.get("niche") != "text-to-sql":
        reasons.append("niche must be text-to-sql")

    difficulty = str(row.get("difficulty", ""))
    if difficulty not in ALLOWED_DIFFICULTIES:
        reasons.append("difficulty must be easy, medium, hard, or expert")
    else:
        dimensions["difficulty_signal"] = {"easy": 4, "medium": 7, "hard": 9, "expert": 10}[difficulty]

    instruction = str(row.get("instruction", ""))
    gold_sql = str(row.get("gold_sql", ""))
    if len(instruction.split()) < 8:
        reasons.append("instruction is too short to be useful")
    if PLACEHOLDER_PATTERNS.search(instruction) or PLACEHOLDER_PATTERNS.search(gold_sql):
        reasons.append("row contains placeholder/meta text")
    if BENCHMARK_NAMES.search(instruction):
        reasons.append("instruction mentions benchmark names, which is a leakage smell")
    if 8 <= len(instruction.split()) <= 120 and not PLACEHOLDER_PATTERNS.search(instruction):
        dimensions["training_value"] = 14
    if not BENCHMARK_NAMES.search(instruction + " " + gold_sql):
        dimensions["leakage_resistance"] = 10

    verifier = row.get("verifier", {})
    ordered = bool(verifier.get("ordered", False)) if isinstance(verifier, Mapping) else False
    tolerance = float(verifier.get("float_tolerance", 1e-6)) if isinstance(verifier, Mapping) else 1e-6

    actual: list[dict[str, Any]] | None = None
    if not reasons or "missing required fields" not in " ".join(reasons):
        try:
            actual = run_select(row["schema"], gold_sql)
            dimensions["sql_execution"] = 25
            metadata["actual_result"] = actual
        except Exception as exc:  # noqa: BLE001 - gate should preserve user-facing reason
            reasons.append(f"SQL execution failed: {exc}")

    expected = row.get("expected_result")
    if actual is not None:
        if not isinstance(expected, list):
            reasons.append("expected_result must be a list of row objects")
        elif _compare_results(actual, expected, ordered=ordered, tolerance=tolerance):
            dimensions["answer_match"] = 21
        else:
            reasons.append("gold_sql result does not match expected_result")

    score = _dimension_score(reasons, dimensions)
    accepted = score >= min_score and not reasons
    if score < min_score and not reasons:
        reasons.append(f"score below threshold: {score} < {min_score}")
    return GateResult(score=score, accepted=accepted, reasons=reasons, dimensions=dimensions, metadata=metadata)
