# DeepSeek Generator Instructions

Generate the requested number of Text-to-SQL candidate rows.

Return:

```json
{
  "rows": []
}
```

Each row must follow the `row_contract` passed by the user.

Hard schema contract:

- `niche` must be exactly `"text-to-sql"`.
- `domain` must be one of the requested domains.
- `schema.tables` must be an array, not an object/map.
- Each table must be `{"name": "...", "columns": [...], "rows": [...]}`.
- `columns` must be an array of `{"name": "...", "type": "INTEGER|REAL|TEXT|BOOLEAN|DATE|DATETIME"}`.
- `rows` must be an array of objects keyed by column name, not arrays of positional values.
- `expected_result` must be an array of objects keyed by the SQL output column aliases.
- Use deterministic dates in both sample data and SQL. Avoid `DATE('now')`, `CURRENT_DATE`, or any runtime-dependent expression.

Canonical shape:

```json
{
  "niche": "text-to-sql",
  "domain": "logistics",
  "difficulty": "medium",
  "skills": ["join", "aggregation"],
  "instruction": "Which carriers completed at least two shipments, and how many did each complete?",
  "schema": {
    "tables": [
      {
        "name": "shipments",
        "columns": [
          {"name": "shipment_id", "type": "INTEGER"},
          {"name": "carrier_id", "type": "INTEGER"},
          {"name": "status", "type": "TEXT"}
        ],
        "rows": [
          {"shipment_id": 1, "carrier_id": 10, "status": "delivered"},
          {"shipment_id": 2, "carrier_id": 10, "status": "delivered"},
          {"shipment_id": 3, "carrier_id": 20, "status": "in_transit"}
        ]
      }
    ]
  },
  "gold_sql": "SELECT carrier_id, COUNT(*) AS completed_shipments FROM shipments WHERE status = 'delivered' GROUP BY carrier_id HAVING COUNT(*) >= 2 ORDER BY completed_shipments DESC;",
  "expected_result": [{"carrier_id": 10, "completed_shipments": 2}],
  "verifier": {"ordered": true, "float_tolerance": 0.000001},
  "generation": {"quality_notes": "Computed by filtering delivered rows and grouping by carrier."}
}
```

For each row:

1. Invent a realistic business schema in the requested domain.
2. Add realistic sample rows. Keep the database small but sufficient.
3. Write a natural-language analytics question.
4. Write one correct SQLite `gold_sql` query.
5. Compute the exact `expected_result`.
6. Add skill labels and a short `generation.quality_notes` note.

Difficulty guidance:

- Easy: one table, simple filter, sort, or aggregation.
- Medium: 2-3 tables with joins and grouping.
- Hard: multi-hop joins, date filtering, conditional aggregation, subquery, or CTE.
- Expert: requires careful NULL handling, anti-joins, set logic, window-like reasoning, or ambiguous column names resolved by schema semantics.

Reject your own row before output if:

- The SQL would not run in SQLite.
- The expected result was guessed instead of computed.
- The answer could be obtained without using the schema.
- The question is generic or unnatural.
- The row resembles a known public benchmark example.
