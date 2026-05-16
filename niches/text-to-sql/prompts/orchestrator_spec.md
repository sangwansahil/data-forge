# Codex Orchestrator Spec

You are generating candidate rows for `data-forge`, a benchmark-backed Text-to-SQL dataset pipeline.

Your job is to create high-value synthetic training examples. Every row will be executed and judged before acceptance, so correctness matters more than volume.

Hard rules:

- Output valid JSON only.
- Output a JSON object with a top-level `rows` array.
- Do not mention benchmark names inside generated row instructions.
- Do not copy public benchmark schemas, questions, or SQL.
- Use SQLite-compatible SQL.
- Every row must include enough table data for the gold SQL to execute locally.
- Every `expected_result` must exactly match the gold SQL result.
- Prefer realistic schemas with 2-5 tables and 5-12 rows per table.
- Include natural business wording, not benchmark-like phrasing.
- Avoid placeholders, toy names like foo/bar, and meta text.
- Make hard rows genuinely hard through schema linking, joins, date logic, NULL behavior, aggregation, or nested queries.

Accepted rows must teach skills that transfer to Spider, BIRD, Spider 2.0, and LiveSQLBench without leaking their examples.
