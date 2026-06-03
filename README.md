# data-forge

`data-forge` is a framework for building high-quality synthetic dataset pipelines.

The core idea is simple: generator models are useful for producing candidate data, but the moat is the quality system around them. Rows are generated, executed or validated, judged against explicit rubrics, reviewed by humans when needed, signed off, and only then exported for training.

This repository is designed to be cloned and adapted for new niches. A niche can be SQL, coding, customer-support tools, browser tasks, legal classification, logistics reasoning, or any other domain where data quality can be measured with clear gates.

## What It Provides

- A reusable storage layer with `local://` and `gdrive://` backends.
- A pattern for niche-specific generation prompts, validators, reports, review packets, and dataset exports.
- Sharded generation for running independent workers in parallel without write races.
- Static HTML review packets for human approval without running a server.
- Signoff enforcement before fine-tuning exports.
- Testable quality gates instead of trust-based synthetic data.
- Data Forge Lab: an agentic visual harness for small-model fine-tuning experiments, with local or Supabase-backed run state.

## Repository Layout

```text
data-forge/
  docs/                 # Framework-level architecture and storage docs
  apps/lab-ui/          # Static Data Forge Lab demo console
  niches/               # Domain-specific dataset factories
  scripts/              # Framework-level helper commands
  src/data_forge/core/  # Reusable storage, scoring, and JSON helpers
  src/data_forge/lab/   # Agentic lab run cards and orchestration contracts
  src/data_forge/niches # Python implementation for niche packs
  tests/                # Core and niche tests
```

Niche-specific scripts and docs live inside each niche folder. The current example niche is under `niches/`.

## Quick Start

Clone and run tests:

```bash
git clone <repo-url>
cd data-forge
python3 -m unittest discover -s tests
for dir in niches/*/tests; do python3 -m unittest discover -s "$dir"; done
```

Install package dependencies:

```bash
python3 -m pip install -e .
```

Use local storage during development:

```bash
export DATA_FORGE_STORAGE=local
```

Use Google Drive as the shared data store:

```bash
export DATA_FORGE_STORAGE=gdrive
export DATA_FORGE_DRIVE_ROOT_ID=<google-drive-folder-id>
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
```

Cloud agents can use:

```bash
export GOOGLE_APPLICATION_CREDENTIALS_JSON='<raw service account json>'
```

See `docs/google_drive_storage.md` for Drive setup.

## Data Forge Lab Demo

Build the current Text-to-SQL proof run card:

```bash
python3 scripts/build_lab_demo.py
```

Open the static Lab UI:

```bash
python3 -m http.server 8765 --directory apps/lab-ui
```

Then visit `http://localhost:8765`.

The Lab demo shows the intended end product: a clean visual agent console where the user writes a prompt, approves major decisions, watches the closed loop, and receives benchmarked model artifacts.

Run the local Lab server with persisted run state and approval APIs:

```bash
PYTHONPATH=src python3 -m data_forge.cli lab serve
```

Then visit `http://127.0.0.1:8765`.

CLI inspection:

```bash
python3 -m data_forge.cli lab inspect
python3 -m data_forge.cli lab demo
python3 -m data_forge.cli lab plan "fine tune a small model for tool calling"
python3 -m data_forge.cli lab run-next <run_id>
```

The default Lab training backend is `dry-run`. It creates checkpoint handoff manifests and local artifacts so the UI can exercise the closed loop, but it does not create model weights or claim model improvement:

```bash
export DATA_FORGE_LAB_TRAIN_BACKEND=dry-run
```

For a hosted/user-facing Lab deployment, use Supabase for run state:

```bash
export DATA_FORGE_LAB_STORE=supabase
export SUPABASE_URL=https://<project-ref>.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=<server-only-service-role-key>
```

Apply `supabase/migrations/20260603000000_data_forge_lab.sql` first. See `docs/supabase_lab_storage.md`.

## Core Workflow

1. Define a niche pack with a row contract, generation prompts, validators, review UI, and export format.
2. Generate raw candidate rows with a cheap or high-throughput generator model.
3. Run deterministic gates and rubric scoring.
4. Archive rejected rows with reasons.
5. For larger runs, generate multiple independent shards and merge/dedupe accepted rows.
6. Build static HTML review packets for accepted rows.
7. Apply human review decisions.
8. Create a signoff manifest.
9. Export only approved rows into training-ready datasets.
10. Evaluate the trained model against public or private benchmarks.

## Building a New Niche

A niche should include:

- `README.md`: domain goal, benchmark target, and usage.
- `config.json`: domains, skills, thresholds, and prompt paths.
- `prompts/`: orchestrator, generator, and judge instructions.
- `examples/`: one accepted row and one rejected row.
- `scripts/`: niche-specific generation, review, signoff, and export commands.
- Python gates under `src/data_forge/niches/<niche_name>/`.
- Tests covering acceptance, rejection, review, signoff, and export.

Keep generated datasets, benchmark downloads, model outputs, adapters, and service-account credentials out of git.

## Design Principle

Fine-tuning is downstream. The asset is the reviewed dataset and the repeatable process that created it.
