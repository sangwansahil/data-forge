# DeepSeek Generator Instructions

Generate the requested number of Text-to-SQL candidate rows.

Return:

```json
{
  "rows": []
}
```

Each row must follow the `row_contract` passed by the user.

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
