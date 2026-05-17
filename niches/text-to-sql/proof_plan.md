# Text-to-SQL Proof Plan

Goal: prove that forged, gated data improves a small model on a public Text-to-SQL benchmark.

## Proof Claim

`data-forge` works if a small base model improves on the same benchmark harness after fine-tuning on the reviewed forged dataset.

First proof:

```text
base 3B-4B model Spider execution accuracy
  vs.
same model fine-tuned on data-forge Text-to-SQL v0.1
```

## Dataset Version

Use the first sharded 1k run as `text-to-sql-v0.1`:

```text
generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/merged/accepted.jsonl
```

Run stats:

- 1,010 merged accepted rows.
- 15 duplicate fingerprints removed.
- Domains balanced across 10 domain shards.
- Score range 94-100.
- Score average 97.6.

## Benchmark

Start with Spider dev because it is small, public, and fast to run locally.

Use the repo's lightweight execution harness for fast iteration, then run the official Spider/Test-Suite evaluator for any public claim.

## Build Prompt Pack

After downloading Spider locally:

```bash
python3 niches/text-to-sql/scripts/build_spider_prompt_pack.py \
  --examples external/spider/dev.json \
  --database-dir external/spider/database \
  --out generation/niches/text-to-sql/evals/spider_dev/prompt_pack.jsonl \
  --sample-rows 0
```

For a cheap smoke:

```bash
python3 niches/text-to-sql/scripts/build_spider_prompt_pack.py \
  --examples external/spider/dev.json \
  --database-dir external/spider/database \
  --out generation/niches/text-to-sql/evals/spider_dev/prompt_pack_50.jsonl \
  --limit 50
```

## Baseline Inference

Install optional eval dependencies:

```bash
python3 -m pip install -e '.[eval]'
```

Run baseline inference:

```bash
python3 niches/text-to-sql/scripts/run_hf_text_to_sql_inference.py \
  --model Qwen/Qwen2.5-Coder-3B-Instruct \
  --input generation/niches/text-to-sql/evals/spider_dev/prompt_pack.jsonl \
  --out generation/niches/text-to-sql/evals/spider_dev/base_predictions.jsonl \
  --temperature 0
```

## Evaluate Predictions

```bash
python3 niches/text-to-sql/scripts/evaluate_sql_predictions.py \
  --predictions generation/niches/text-to-sql/evals/spider_dev/base_predictions.jsonl \
  --database-dir external/spider/database \
  --out generation/niches/text-to-sql/evals/spider_dev/base_eval
```

This writes:

```text
report.json
per_example.jsonl
```

## Fine-Tune

Export the forged dataset to SFT chat JSONL:

```bash
python3 niches/text-to-sql/scripts/export_text_to_sql_dataset.py \
  --input local://generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/merged/accepted.jsonl \
  --out local://generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/datasets/sft_sql_only \
  --unsafe-skip-review-signoff \
  --force
```

Then fine-tune the same base model with LoRA/QLoRA using:

```text
generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/datasets/sft_sql_only/train.jsonl
generation/niches/text-to-sql/runs/t2sql_parallel_1k_001/datasets/sft_sql_only/validation.jsonl
```

## Fine-Tuned Eval

Run inference again with the fine-tuned adapter or merged model:

```bash
python3 niches/text-to-sql/scripts/run_hf_text_to_sql_inference.py \
  --model <fine-tuned-model-or-adapter-merged-model> \
  --input generation/niches/text-to-sql/evals/spider_dev/prompt_pack.jsonl \
  --out generation/niches/text-to-sql/evals/spider_dev/finetuned_predictions.jsonl \
  --temperature 0
```

Evaluate:

```bash
python3 niches/text-to-sql/scripts/evaluate_sql_predictions.py \
  --predictions generation/niches/text-to-sql/evals/spider_dev/finetuned_predictions.jsonl \
  --database-dir external/spider/database \
  --out generation/niches/text-to-sql/evals/spider_dev/finetuned_eval
```

Compare base vs fine-tuned:

```bash
python3 niches/text-to-sql/scripts/compare_eval_reports.py \
  --base-report generation/niches/text-to-sql/evals/spider_dev/base_eval/report.json \
  --finetuned-report generation/niches/text-to-sql/evals/spider_dev/finetuned_eval/report.json \
  --out generation/niches/text-to-sql/evals/spider_dev/comparison.json
```

## Success Criteria

First proof succeeds if either condition holds:

- Fine-tuned execution accuracy improves by at least 5 absolute points over the base model.
- Fine-tuned model improves clearly on targeted slices such as joins, aggregation, date logic, null handling, or schema-linking traps.

Only after this first proof should the project scale to 5k+ rows or compare directly against frontier models.
