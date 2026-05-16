# Pilot Batch 001

Purpose: prove that the row contract and gates can produce useful Text-to-SQL fine-tuning data.

Raw target: 100 rows.

Accepted target: 25 rows.

Acceptance threshold: 85.

Domains:

- ecommerce
- logistics
- support operations
- SaaS metrics
- warehouse inventory

Skill targets:

- 20% joins
- 20% aggregation
- 15% date logic
- 10% conditional aggregation
- 10% top-k
- 10% subqueries or CTEs
- 10% schema-linking traps
- 5% NULL handling

Reject patterns to watch:

- Expected result guessed incorrectly.
- SQL uses unsupported SQLite functions.
- Question can be answered from table or column names alone.
- Too many rows with the same schema shape.
- Overuse of simple `COUNT(*)` questions.
