# Dataset Contract

Each accepted row must be a JSON object with these fields:

```json
{
  "id": "t2sql_000001",
  "niche": "text-to-sql",
  "domain": "ecommerce",
  "difficulty": "medium",
  "skills": ["join", "aggregation", "top_k"],
  "instruction": "Which three customers spent the most on completed orders in March 2026?",
  "schema": {
    "dialect": "sqlite",
    "tables": [
      {
        "name": "customers",
        "columns": [
          {"name": "customer_id", "type": "INTEGER"},
          {"name": "name", "type": "TEXT"}
        ],
        "rows": [
          {"customer_id": 1, "name": "Avery Stone"}
        ]
      }
    ]
  },
  "gold_sql": "SELECT ...",
  "expected_result": [
    {"name": "Avery Stone", "total_spend": 124.5}
  ],
  "verifier": {
    "type": "sqlite_exact",
    "ordered": true,
    "float_tolerance": 0.000001
  },
  "generation": {
    "generator_model": "deepseek-chat",
    "batch_id": "pilot_001",
    "quality_notes": "..."
  }
}
```

## Acceptance bar

A row is accepted only if:

- The JSON contract is valid.
- SQL is read-only and executable.
- Query output matches `expected_result`.
- The instruction is natural and specific.
- The row is not a duplicate.
- The row does not mention or copy benchmark names.
- The programmatic judge score is at least 85.

## Fine-tuning formats

Rows can be converted into several training targets:

### Direct SQL SFT

```json
{"messages":[{"role":"system","content":"You write correct SQLite SQL only."},{"role":"user","content":"Schema: ...\nQuestion: ..."},{"role":"assistant","content":"SELECT ..."}]}
```

### Reasoned SQL SFT

Use only if the target model is intended to produce short private plans or the training stack supports hidden reasoning. Otherwise keep the assistant output to SQL.

### SQL repair

For BIRD-Critic/SWE-SQL style follow-up packs:

```json
{"broken_sql":"...","error":"...","gold_sql":"..."}
```
