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

## Repository Layout

```text
data-forge/
  docs/                 # Framework-level architecture and storage docs
  niches/               # Domain-specific dataset factories
  src/data_forge/core/  # Reusable storage, scoring, and JSON helpers
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
