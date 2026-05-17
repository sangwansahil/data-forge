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

The first proof-of-work milestone is smaller: freeze the first sharded 1k dataset, run a base model on Spider dev, fine-tune that same model on the forged data, and rerun the same eval. See `proof_plan.md` and `local_baseline_mlx.md`.

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

Run sharded local generation:

```bash
export DEEPSEEK_API_KEY=...

python3 niches/text-to-sql/scripts/run_text_to_sql_sharded.py \
  --run-id t2sql_parallel_1k_001 \
  --target-accepted-total 1000 \
  --shard-count 10 \
  --parallelism 5 \
  --batch-size 5 \
  --max-batches-per-shard 80 \
  --storage local
```

The sharded runner creates one independent run per domain slice under:

```text
generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/shards/
```

After all shards finish, it merges accepted rows into:

```text
generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/merged/accepted.jsonl
generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/merged/duplicates.jsonl
generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/merged/merge_manifest.json
```

Use `--parallelism` to control API concurrency. Start with `5`; increase only after the API is stable.

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

Build a Spider prompt pack and evaluate predictions:

```bash
python3 niches/text-to-sql/scripts/build_spider_prompt_pack.py \
  --examples external/spider/dev.json \
  --database-dir external/spider/database \
  --out generation/niches/text-to-sql/evals/spider_dev/prompt_pack.jsonl

python3 niches/text-to-sql/scripts/evaluate_sql_predictions.py \
  --predictions generation/niches/text-to-sql/evals/spider_dev/predictions.jsonl \
  --database-dir external/spider/database \
  --out generation/niches/text-to-sql/evals/spider_dev/eval
```

Run local MLX inference on Apple Silicon:

```bash
python3 niches/text-to-sql/scripts/run_mlx_text_to_sql_inference.py \
  --model mlx-community/Qwen3-4B-Instruct-2507-4bit \
  --input generation/niches/text-to-sql/evals/spider_dev/prompt_pack.jsonl \
  --out generation/niches/text-to-sql/evals/spider_dev/qwen4b_base_predictions.jsonl
```

Run a local Qwen3.5-4B LoRA fine-tune on Apple Silicon:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e ".[train]"

.venv/bin/python niches/text-to-sql/scripts/train_qwen35_lora_local.py \
  --model Qwen/Qwen3.5-4B \
  --train generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/datasets/sft_sql_only/train.jsonl \
  --validation generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/datasets/sft_sql_only/validation.jsonl \
  --out generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/models/qwen35_4b_lora_mps_float32_200 \
  --dtype float32 \
  --max-steps 200 \
  --max-length 768 \
  --batch-size 1 \
  --grad-accum 8 \
  --lr 0.00005 \
  --eval-every 50 \
  --eval-batches 0 \
  --no-validation
```

Use `float32` on MPS for stability. `float16` is faster but can produce non-finite losses on this model path.
