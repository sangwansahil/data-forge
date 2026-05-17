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
    if declared.startswith(("DECIMAL", "NUMERIC", "REAL", "FLOAT", "DOUBLE")):
        return "REAL"
    if declared.startswith(("INTEGER", "INT", "BIGINT", "SMALLINT")):
        return "INTEGER"
    if declared.startswith(("TEXT", "VARCHAR", "CHAR", "STRING")):
        return "TEXT"
    if declared.startswith(("DATE", "DATETIME", "TIMESTAMP")):
        return "TEXT"
    if declared.startswith(("BOOLEAN", "BOOL")):
        return "INTEGER"
    raise ValueError(f"unsupported column type: {declared}")


def _normalize_tables(schema: Mapping[str, Any]) -> list[dict[str, Any]]:
    tables = schema.get("tables", schema)
    if isinstance(tables, Mapping):
        tables = [dict(table, name=name) for name, table in tables.items() if isinstance(table, Mapping)]
    if not isinstance(tables, list) or not tables:
        raise ValueError("schema.tables must be a non-empty list")
    return tables


def _normalize_columns(columns: Any) -> list[dict[str, Any]]:
    if isinstance(columns, Mapping):
        return [{"name": name, "type": column_type} for name, column_type in columns.items()]
    if not isinstance(columns, list) or not columns:
        raise ValueError("table.columns must be a non-empty list or mapping")
    normalized = []
    for column in columns:
        if isinstance(column, str):
            normalized.append({"name": column, "type": "TEXT"})
        elif isinstance(column, Mapping):
            normalized.append(dict(column))
        else:
            raise ValueError("each column must be an object or column name")
    return normalized


def build_sqlite_connection(schema: Mapping[str, Any]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    tables = _normalize_tables(schema)

    for table in tables:
        if not isinstance(table, Mapping):
            raise ValueError("each table must be an object")
        table_name = _quote_identifier(str(table.get("name", "")))
        columns = _normalize_columns(table.get("columns", []))
        column_defs = []
        column_names = []
        for column in columns:
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
                if isinstance(row, Mapping):
                    values.append([row.get(name) for name in column_names])
                elif isinstance(row, Sequence) and not isinstance(row, (str, bytes)):
                    values.append(list(row))
                else:
                    raise ValueError("table row must be an object or value list")
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
