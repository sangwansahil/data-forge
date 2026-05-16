# Architecture

`data-forge` separates generation from admission.

DeepSeek is allowed to be creative. The gates are not. Candidate rows can be verbose, imperfect, and diverse in the raw archive, but accepted rows must be deterministic, executable, and useful for fine-tuning.

## Core objects

- `BatchPlan`: the Codex-authored plan for one generation batch.
- `CandidateRow`: one generated training example.
- `GateResult`: deterministic pass/fail checks and scored rubric dimensions.
- `AcceptedRow`: a candidate row with judge metadata attached.
- `RejectedRow`: a candidate row plus rejection reasons.

## Quality gates

Every niche pack should implement these layers:

1. **Schema gate**: required fields, valid labels, known dialects, stable IDs.
2. **Executable gate**: code/SQL/tool trace runs in a sandbox.
3. **Answer gate**: output matches expected result under declared tolerance.
4. **Diversity gate**: row is not a duplicate of prior accepted rows.
5. **Leakage gate**: row is not copied from benchmark examples.
6. **Rubric judge**: programmatic score for training value.

For Text-to-SQL, the executable gate uses SQLite first because it is cheap and local. Later packs can add Postgres, DuckDB, Snowflake, or BigQuery adapters.

## Data policy

Do not train on public benchmark test/dev rows. The point is to teach transferable skills, then prove them on public benchmarks. Benchmark examples can inform taxonomies and difficulty targets, but not row text or gold SQL.
