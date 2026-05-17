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
SQL_STRING = re.compile(r"'(?:''|[^'])*'")
SQL_FUNCTION = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
SQL_TABLE_ALIAS = re.compile(
    r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:AS\s+)?([A-Za-z_][A-Za-z0-9_]*)?",
    re.IGNORECASE,
)
SQL_QUALIFIED_COLUMN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\b")
SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SQL_KEYWORDS = {
    "as",
    "by",
    "case",
    "cast",
    "count",
    "date",
    "desc",
    "else",
    "end",
    "from",
    "group",
    "having",
    "in",
    "join",
    "left",
    "like",
    "limit",
    "max",
    "min",
    "not",
    "null",
    "on",
    "order",
    "over",
    "partition",
    "select",
    "sum",
    "then",
    "when",
    "where",
    "with",
}
ALLOWED_SQLITE_FUNCTIONS = {
    "abs",
    "avg",
    "coalesce",
    "count",
    "date",
    "datetime",
    "ifnull",
    "instr",
    "julianday",
    "length",
    "lower",
    "max",
    "min",
    "nullif",
    "printf",
    "round",
    "strftime",
    "substr",
    "substring",
    "sum",
    "time",
    "total",
    "trim",
    "upper",
}
SQLITE_FUNCTION_ARITY = {
    "abs": (1, 1),
    "avg": (1, 1),
    "coalesce": (2, None),
    "count": (0, 1),
    "date": (1, None),
    "datetime": (1, None),
    "ifnull": (2, 2),
    "instr": (2, 2),
    "julianday": (1, None),
    "length": (1, 1),
    "lower": (1, 1),
    "max": (1, None),
    "min": (1, None),
    "nullif": (2, 2),
    "printf": (1, None),
    "round": (1, 2),
    "strftime": (2, None),
    "substr": (2, 3),
    "substring": (2, 3),
    "sum": (1, 1),
    "time": (1, None),
    "total": (1, 1),
    "trim": (1, 2),
    "upper": (1, 1),
}


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
    expected: Sequence[Any],
    *,
    ordered: bool,
    tolerance: float,
) -> bool:
    left = normalize_result(actual, ordered=ordered)
    if len(left) != len(expected):
        return False
    if all(isinstance(row, Mapping) for row in expected):
        right = normalize_result(expected, ordered=ordered)
        for actual_row, expected_row in zip(left, right):
            if set(actual_row) != set(expected_row):
                return False
            for key in expected_row:
                if not _compare_values(actual_row[key], expected_row[key], tolerance):
                    return False
        return True
    if not ordered:
        left = sorted(left, key=lambda item: repr(list(item.values())))
        expected = sorted(expected, key=repr)
    for actual_row, expected_row in zip(left, expected):
        if not isinstance(expected_row, Sequence) or isinstance(expected_row, (str, bytes)):
            return False
        actual_values = list(actual_row.values())
        expected_values = list(expected_row)
        if len(actual_values) != len(expected_values):
            return False
        for actual_value, expected_value in zip(actual_values, expected_values):
            if not _compare_values(actual_value, expected_value, tolerance):
                return False
    return True


def _dimension_score(reasons: list[str], dimensions: dict[str, int]) -> int:
    score = sum(dimensions.values())
    if reasons:
        score = min(score, 84)
    return max(0, min(100, score))


def _schema_columns(schema: Any) -> dict[str, set[str]]:
    if not isinstance(schema, Mapping):
        return {}
    tables = schema.get("tables", [])
    if isinstance(tables, Mapping):
        tables = [dict(table, name=name) for name, table in tables.items() if isinstance(table, Mapping)]
    columns_by_table: dict[str, set[str]] = {}
    if not isinstance(tables, Sequence) or isinstance(tables, (str, bytes)):
        return columns_by_table
    for table in tables:
        if not isinstance(table, Mapping):
            continue
        table_name = str(table.get("name", ""))
        columns = table.get("columns", [])
        names: set[str] = set()
        if isinstance(columns, Mapping):
            names.update(str(name) for name in columns)
        elif isinstance(columns, Sequence) and not isinstance(columns, (str, bytes)):
            for column in columns:
                if isinstance(column, Mapping):
                    names.add(str(column.get("name", "")))
                elif isinstance(column, str):
                    names.add(column)
        if table_name:
            columns_by_table[table_name.lower()] = {name.lower() for name in names if name}
    return columns_by_table


def _strip_sql_strings(sql: str) -> str:
    return SQL_STRING.sub("''", sql)


def _extract_parenthesized(sql: str, open_index: int) -> str | None:
    depth = 0
    start = open_index + 1
    for index in range(open_index, len(sql)):
        char = sql[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return sql[start:index]
    return None


def _count_args(argument_sql: str) -> int:
    stripped = argument_sql.strip()
    if not stripped:
        return 0
    depth = 0
    count = 1
    for char in stripped:
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "," and depth == 0:
            count += 1
    return count


def _sql_static_reasons(row: Mapping[str, Any], actual: Sequence[Mapping[str, Any]] | None) -> list[str]:
    reasons: list[str] = []
    gold_sql = str(row.get("gold_sql", ""))
    sql = _strip_sql_strings(gold_sql)
    schema_columns = _schema_columns(row.get("schema"))

    alias_to_table: dict[str, str] = {}
    for table, alias in SQL_TABLE_ALIAS.findall(sql):
        table_key = table.lower()
        alias_key = (alias or table).lower()
        if table_key not in schema_columns:
            reasons.append(f"SQL references unknown table: {table}")
            continue
        alias_to_table[table_key] = table_key
        if alias_key not in SQL_KEYWORDS:
            alias_to_table[alias_key] = table_key

    for qualifier, column in SQL_QUALIFIED_COLUMN.findall(sql):
        qualifier_key = qualifier.lower()
        column_key = column.lower()
        if qualifier_key not in alias_to_table:
            reasons.append(f"SQL references unknown table alias: {qualifier}")
            continue
        table_key = alias_to_table[qualifier_key]
        if column_key not in schema_columns.get(table_key, set()):
            reasons.append(f"SQL references unknown column for alias {qualifier}: {column}")

    for match in SQL_FUNCTION.finditer(sql):
        function = match.group(1).lower()
        if function in SQL_KEYWORDS:
            continue
        if function not in ALLOWED_SQLITE_FUNCTIONS:
            reasons.append(f"unsupported SQLite function: {function}")
            continue
        args = _extract_parenthesized(sql, match.end() - 1)
        if args is None:
            reasons.append(f"malformed SQLite function call: {function}")
            continue
        arg_count = _count_args(args)
        min_args, max_args = SQLITE_FUNCTION_ARITY[function]
        if arg_count < min_args or (max_args is not None and arg_count > max_args):
            if max_args is None:
                expected = f"at least {min_args}"
            elif min_args == max_args:
                expected = str(min_args)
            else:
                expected = f"{min_args}-{max_args}"
            reasons.append(f"wrong SQLite function arity for {function}: got {arg_count}, expected {expected}")

    if actual:
        for column in actual[0].keys():
            if not SQL_IDENTIFIER.fullmatch(str(column)):
                reasons.append(f"SQL output column needs a stable alias: {column}")
    return sorted(set(reasons))


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
        metadata["niche_warning"] = f"expected text-to-sql, got {row.get('niche')!r}"

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

    reasons.extend(_sql_static_reasons(row, actual))

    expected = row.get("expected_result")
    if actual is not None:
        if not isinstance(expected, list):
            reasons.append("expected_result must be a list of row objects or value lists")
        elif _compare_results(actual, expected, ordered=ordered, tolerance=tolerance):
            dimensions["answer_match"] = 21
        else:
            reasons.append("gold_sql result does not match expected_result")

    score = _dimension_score(reasons, dimensions)
    accepted = score >= min_score and not reasons
    if score < min_score and not reasons:
        reasons.append(f"score below threshold: {score} < {min_score}")
    return GateResult(score=score, accepted=accepted, reasons=reasons, dimensions=dimensions, metadata=metadata)
