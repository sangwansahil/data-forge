# data-forge

Benchmark-backed dataset generation pipelines for training small specialist models.

`data-forge` is built around one principle: synthetic rows do not enter a training set until they pass executable quality gates. A generator model such as DeepSeek can produce candidates cheaply, but every row is treated as untrusted raw material until deterministic checks and a Codex rubric judge approve it.

## First niche

The first niche pack is `niches/text-to-sql`.

Goal: generate a world-class Text-to-SQL fine-tuning dataset for a small open model such as Qwen3.5-4B, then prove the system works on public benchmarks.

Benchmark ladder:

1. Spider 1.0 dev for fast local iteration.
2. BIRD dev for real database schemas, external knowledge, and execution accuracy.
3. Spider 2.0 Lite/Snow for enterprise workflow difficulty.
4. LiveSQLBench for contamination-resistant public evaluation.

The training data should not copy benchmark rows. The pack generates synthetic schemas and questions that teach the underlying skills: schema linking, joins, aggregation, nested queries, date logic, ambiguity handling, and dialect-aware SQL.

## Repository layout

```text
data-forge/
  niches/
    text-to-sql/              # Human-facing niche spec, prompts, configs, examples
  src/data_forge/             # Reusable Python gates and CLI
  scripts/                    # Batch generation and validation entrypoints
  tests/                      # Gate tests
```

## Quick start

Validate the example row:

```bash
python scripts/validate_text_to_sql_batch.py niches/text-to-sql/examples/accepted_row.json --min-score 85
```

Run tests:

```bash
python -m unittest discover -s tests
```

Generate a raw batch with DeepSeek:

```bash
export DEEPSEEK_API_KEY=...
python scripts/generate_text_to_sql_batch.py \
  --config niches/text-to-sql/config.json \
  --batch-id pilot_001 \
  --rows 20 \
  --out generation/raw/pilot_001.jsonl
```

Then validate the generated batch:

```bash
python scripts/validate_text_to_sql_batch.py generation/raw/pilot_001.jsonl \
  --accepted generation/accepted/pilot_001.jsonl \
  --rejected generation/rejected/pilot_001.jsonl \
  --report generation/reports/pilot_001.json \
  --min-score 85
```

## Google Drive storage

Generated datasets can live in Google Drive so local and cloud agents share the same source of truth. Configure a service account, share one Drive folder with that service-account email, then set:

```bash
export DEEPSEEK_API_KEY=...
export DATA_FORGE_STORAGE=gdrive
export DATA_FORGE_DRIVE_ROOT_ID=<google-drive-folder-id>
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

Cloud agents can use:

```bash
export GOOGLE_APPLICATION_CREDENTIALS_JSON='<raw service account json>'
```

Run a storage-aware generation loop:

```bash
python3 scripts/run_text_to_sql_loop.py \
  --config niches/text-to-sql/config.json \
  --run-id t2sql_pilot_001 \
  --target-accepted 5000 \
  --batch-size 100 \
  --storage gdrive \
  --drive-root-id "$DATA_FORGE_DRIVE_ROOT_ID"
```

Build review packets:

```bash
python3 scripts/build_text_to_sql_review_viewer.py \
  --run-id t2sql_pilot_001 \
  --input gdrive://niches/text-to-sql/runs/t2sql_pilot_001/accepted \
  --out gdrive://niches/text-to-sql/runs/t2sql_pilot_001/review
```

Apply review decisions, sign off, and export:

```bash
python3 scripts/apply_text_to_sql_review.py \
  --run-id t2sql_pilot_001 \
  --accepted gdrive://niches/text-to-sql/runs/t2sql_pilot_001/accepted \
  --decisions gdrive://niches/text-to-sql/runs/t2sql_pilot_001/review/decisions \
  --out gdrive://niches/text-to-sql/runs/t2sql_pilot_001/reviewed

python3 scripts/signoff_text_to_sql_dataset.py \
  --run-id t2sql_pilot_001 \
  --reviewed gdrive://niches/text-to-sql/runs/t2sql_pilot_001/reviewed \
  --reviewer sahil \
  --out gdrive://niches/text-to-sql/runs/t2sql_pilot_001/manifests/signoff.json

python3 scripts/export_text_to_sql_dataset.py \
  --input gdrive://niches/text-to-sql/runs/t2sql_pilot_001/reviewed/approved.jsonl \
  --signoff gdrive://niches/text-to-sql/runs/t2sql_pilot_001/manifests/signoff.json \
  --out gdrive://niches/text-to-sql/runs/t2sql_pilot_001/datasets/sft_sql_only
```

## Row lifecycle

1. Codex writes a batch plan with target skills and anti-leakage constraints.
2. DeepSeek generates candidate rows.
3. Static gates validate schema, metadata, and formatting.
4. SQL gates execute the gold query in an isolated SQLite database.
5. Result gates compare query output to the expected answer.
6. Programmatic judge scores the row against a rubric.
7. Rejected rows are archived with reasons.
8. Accepted rows are reviewed in static HTML packets.
9. Human-approved rows are signed off and exported for fine-tuning.

The first milestone is not "lots of data." It is a small, brutally filtered dataset whose rows are individually useful.
