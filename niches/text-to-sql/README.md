# Text-to-SQL Niche Pack

This pack generates synthetic Text-to-SQL training rows designed to transfer to public benchmarks without copying them.

## Target capability

Train a small model to convert natural business questions into correct SQL across unfamiliar schemas.

The first model target is Qwen3.5-4B or another permissive 2B-4B base/instruct model. The benchmark target is high execution accuracy on public Text-to-SQL evals.

## Public benchmark targets

- Spider 1.0: fast sanity check for classic cross-domain Text-to-SQL.
- BIRD: real database values, larger schemas, and external knowledge.
- Spider 2.0: enterprise-style Text-to-SQL workflows.
- LiveSQLBench: dynamic and contamination-resistant evaluation.

## Dataset principles

- Generate synthetic schemas, rows, questions, gold SQL, and expected query results.
- Prefer executable verification over LLM-only judgment.
- Include rejected examples so the orchestrator can learn what failed.
- Track skill labels per row so the training mix can be adjusted.
- Do not include public benchmark text, schemas, or gold SQL in training data.

## Skill taxonomy

- Basic selection and filtering.
- Single and multi-table joins.
- Aggregation and grouping.
- Sorting, top-k, and limits.
- Date/time filtering and bucketing.
- Conditional aggregation.
- Subqueries and common table expressions.
- Set operations.
- Ambiguity handling.
- Schema-linking traps.
- Numeric precision and NULL behavior.
- Dialect-specific repair.

## First milestone

Produce 5,000 accepted rows with at least an 85/100 programmatic judge score, then fine-tune a 4B model and evaluate it against its base model on Spider dev and BIRD dev using the same prompt/harness.

## Commands

Validate a seed row:

```bash
python3 niches/text-to-sql/scripts/validate_text_to_sql_batch.py \
  niches/text-to-sql/examples/accepted_row.json \
  --min-score 85
```

Run a Drive-backed generation loop:

```bash
python3 niches/text-to-sql/scripts/run_text_to_sql_loop.py \
  --config niches/text-to-sql/config.json \
  --run-id t2sql_pilot_001 \
  --target-accepted 5000 \
  --batch-size 100 \
  --storage gdrive \
  --drive-root-id "$DATA_FORGE_DRIVE_ROOT_ID"
```

Build review packets:

```bash
python3 niches/text-to-sql/scripts/build_text_to_sql_review_viewer.py \
  --run-id t2sql_pilot_001 \
  --input gdrive://niches/text-to-sql/runs/t2sql_pilot_001/accepted \
  --out gdrive://niches/text-to-sql/runs/t2sql_pilot_001/review
```

Apply review decisions, sign off, and export:

```bash
python3 niches/text-to-sql/scripts/apply_text_to_sql_review.py \
  --run-id t2sql_pilot_001 \
  --accepted gdrive://niches/text-to-sql/runs/t2sql_pilot_001/accepted \
  --decisions gdrive://niches/text-to-sql/runs/t2sql_pilot_001/review/decisions \
  --out gdrive://niches/text-to-sql/runs/t2sql_pilot_001/reviewed

python3 niches/text-to-sql/scripts/signoff_text_to_sql_dataset.py \
  --run-id t2sql_pilot_001 \
  --reviewed gdrive://niches/text-to-sql/runs/t2sql_pilot_001/reviewed \
  --reviewer reviewer \
  --out gdrive://niches/text-to-sql/runs/t2sql_pilot_001/manifests/signoff.json

python3 niches/text-to-sql/scripts/export_text_to_sql_dataset.py \
  --input gdrive://niches/text-to-sql/runs/t2sql_pilot_001/reviewed/approved.jsonl \
  --signoff gdrive://niches/text-to-sql/runs/t2sql_pilot_001/manifests/signoff.json \
  --out gdrive://niches/text-to-sql/runs/t2sql_pilot_001/datasets/sft_sql_only
```
