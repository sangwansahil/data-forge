from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any


def schema_to_prompt(schema: Mapping[str, Any]) -> str:
    lines = [f"Dialect: {schema.get('dialect', 'sqlite')}", "", "Schema:"]
    for table in schema.get("tables", []):
        table_name = table["name"]
        columns = table.get("columns", [])
        column_sql = ", ".join(f"{column['name']} {column.get('type', 'TEXT')}" for column in columns)
        lines.append(f"CREATE TABLE {table_name} ({column_sql});")
        rows = table.get("rows", [])
        if rows:
            preview = rows[:5]
            lines.append(f"Sample rows for {table_name}:")
            for row in preview:
                lines.append(json.dumps(row, sort_keys=True))
        lines.append("")
    return "\n".join(lines).strip()


def row_to_sft_record(row: Mapping[str, Any]) -> dict[str, Any]:
    user_content = (
        f"{schema_to_prompt(row['schema'])}\n\n"
        f"Question:\n{row['instruction']}\n\n"
        "Return one SQLite query. Do not include explanation."
    )
    return {
        "messages": [
            {
                "role": "system",
                "content": "You are an expert Text-to-SQL model. Return correct, executable SQLite SQL only.",
            },
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": row["gold_sql"].strip()},
        ],
        "metadata": {
            "source_id": row["id"],
            "domain": row.get("domain"),
            "difficulty": row.get("difficulty"),
            "skills": row.get("skills", []),
        },
    }
