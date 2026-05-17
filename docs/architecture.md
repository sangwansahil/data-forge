# Architecture

`data-forge` separates generation from admission.

Generator models are allowed to be creative. The gates are not. Candidate rows can be verbose, imperfect, and diverse in the raw archive, but accepted rows must be deterministic, validated, and useful for training.

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

Each niche owns its executable or deterministic validation layer. Examples include SQL execution, code tests, API state checks, schema validation, or benchmark-specific scoring.

## Data policy

Do not train on public benchmark test/dev rows. The point is to teach transferable skills, then prove them on public benchmarks. Benchmark examples can inform taxonomies and difficulty targets, but not row text or gold SQL.

## Sharded generation

Large dataset runs should use independent shards instead of one large serial generator loop.

Each shard writes to a unique run path:

```text
runs/{run_id}/
  shards/
    {run_id}_shard_01_<slice>/
      raw/
      accepted/
      rejected/
      reports/
    {run_id}_shard_02_<slice>/
      ...
  merged/
    accepted.jsonl
    duplicates.jsonl
    merge_manifest.json
  review/
```

This avoids write races, makes retries cheap, and lets each shard target a different domain, task family, skill mix, or difficulty band. Shards can run concurrently as local subprocesses, cloud jobs, or agent-managed workers. The merge step is deterministic: accepted rows are fingerprinted, duplicates are removed, and one merged manifest records shard counts, duplicate counts, score summaries, and distribution summaries.

Do not have multiple workers write to the same `raw/`, `accepted/`, `rejected/`, or `reports/` directory. Parallelism should happen across shard directories, followed by merge and review.
