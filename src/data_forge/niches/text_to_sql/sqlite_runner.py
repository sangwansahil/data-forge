from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

SAFE_FIRST_TOKENS = {"select", "with"}
DISALLOWED_SQL = re.compile(
    r"\b(attach|detach|create|drop|alter|insert|update|delete|replace|pragma|vacuum|reindex)\b",
    re.IGNORECASE,
)


class SqlSafetyError(ValueError):
    pass


def assert_safe_select(sql: str) -> None:
    stripped = sql.strip()
    if not stripped:
        raise SqlSafetyError("SQL is empty")
    if ";" in stripped[:-1]:
        raise SqlSafetyError("multiple SQL statements are not allowed")
    first_token = stripped.split(None, 1)[0].lower()
    if first_token not in SAFE_FIRST_TOKENS:
        raise SqlSafetyError("only SELECT/WITH queries are allowed")
    if DISALLOWED_SQL.search(stripped):
        raise SqlSafetyError("query contains a disallowed SQL operation")


def _quote_identifier(identifier: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"unsafe identifier: {identifier!r}")
    return f'"{identifier}"'


def _column_type(column: Mapping[str, Any]) -> str:
    declared = str(column.get("type", "TEXT")).upper()
    allowed = {"INTEGER", "REAL", "TEXT", "BOOLEAN", "DATE", "DATETIME"}
    if declared not in allowed:
        raise ValueError(f"unsupported column type: {declared}")
    if declared in {"DATE", "DATETIME"}:
        return "TEXT"
    if declared == "BOOLEAN":
        return "INTEGER"
    return declared


def build_sqlite_connection(schema: Mapping[str, Any]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    tables = schema.get("tables", [])
    if not isinstance(tables, list) or not tables:
        raise ValueError("schema.tables must be a non-empty list")

    for table in tables:
        if not isinstance(table, Mapping):
            raise ValueError("each table must be an object")
        table_name = _quote_identifier(str(table.get("name", "")))
        columns = table.get("columns", [])
        if not isinstance(columns, list) or not columns:
            raise ValueError("table.columns must be a non-empty list")
        column_defs = []
        column_names = []
        for column in columns:
            if not isinstance(column, Mapping):
                raise ValueError("each column must be an object")
            name = str(column.get("name", ""))
            column_names.append(name)
            column_defs.append(f"{_quote_identifier(name)} {_column_type(column)}")
        conn.execute(f"CREATE TABLE {table_name} ({', '.join(column_defs)})")

        rows = table.get("rows", [])
        if rows is None:
            rows = []
        if not isinstance(rows, list):
            raise ValueError("table.rows must be a list")
        if rows:
            placeholders = ", ".join(["?"] * len(column_names))
            quoted_columns = ", ".join(_quote_identifier(name) for name in column_names)
            insert_sql = f"INSERT INTO {table_name} ({quoted_columns}) VALUES ({placeholders})"
            values = []
            for row in rows:
                if not isinstance(row, Mapping):
                    raise ValueError("table row must be an object")
                values.append([row.get(name) for name in column_names])
            conn.executemany(insert_sql, values)

    return conn


def run_select(schema: Mapping[str, Any], sql: str) -> list[dict[str, Any]]:
    assert_safe_select(sql)
    conn = build_sqlite_connection(schema)
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def normalize_result(result: Sequence[Mapping[str, Any]], ordered: bool) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in result:
        normalized.append({str(key): value for key, value in row.items()})
    if ordered:
        return normalized
    return sorted(normalized, key=lambda item: repr(sorted(item.items())))
