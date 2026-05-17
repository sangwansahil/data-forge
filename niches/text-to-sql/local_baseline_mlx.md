# Local Baseline: Qwen 4B on Apple Silicon

Purpose: get a clean pre-fine-tune baseline on your Mac before training anything.

## Model

Use an MLX quantized 4B instruct model:

```text
mlx-community/Qwen3-4B-Instruct-2507-4bit
```

This is the practical local target for a 64 GB Apple Silicon machine. If you meant a different Qwen 3.x/3.6 checkpoint, swap the `--model` value but keep the same harness.

## Metrics

Report only these first:

1. Execution accuracy.
2. Invalid SQL rate.
3. Total examples evaluated.
4. Wall-clock runtime.

## Setup

```bash
python3 -m pip install -e '.[mlx]'
```

Download Spider into:

```text
external/spider/
  dev.json
  database/
```

## 50-Example Smoke

```bash
python3 niches/text-to-sql/scripts/build_spider_prompt_pack.py \
  --examples external/spider/dev.json \
  --database-dir external/spider/database \
  --out generation/niches/text-to-sql/evals/spider_dev/qwen4b_prompt_pack_50.jsonl \
  --limit 50

time python3 niches/text-to-sql/scripts/run_mlx_text_to_sql_inference.py \
  --model mlx-community/Qwen3-4B-Instruct-2507-4bit \
  --input generation/niches/text-to-sql/evals/spider_dev/qwen4b_prompt_pack_50.jsonl \
  --out generation/niches/text-to-sql/evals/spider_dev/qwen4b_base_predictions_50.jsonl \
  --temperature 0

python3 niches/text-to-sql/scripts/evaluate_sql_predictions.py \
  --predictions generation/niches/text-to-sql/evals/spider_dev/qwen4b_base_predictions_50.jsonl \
  --database-dir external/spider/database \
  --out generation/niches/text-to-sql/evals/spider_dev/qwen4b_base_eval_50
```

## Full Spider Dev Baseline

Run this only after the 50-example smoke is valid:

```bash
python3 niches/text-to-sql/scripts/build_spider_prompt_pack.py \
  --examples external/spider/dev.json \
  --database-dir external/spider/database \
  --out generation/niches/text-to-sql/evals/spider_dev/qwen4b_prompt_pack.jsonl

time python3 niches/text-to-sql/scripts/run_mlx_text_to_sql_inference.py \
  --model mlx-community/Qwen3-4B-Instruct-2507-4bit \
  --input generation/niches/text-to-sql/evals/spider_dev/qwen4b_prompt_pack.jsonl \
  --out generation/niches/text-to-sql/evals/spider_dev/qwen4b_base_predictions.jsonl \
  --temperature 0

python3 niches/text-to-sql/scripts/evaluate_sql_predictions.py \
  --predictions generation/niches/text-to-sql/evals/spider_dev/qwen4b_base_predictions.jsonl \
  --database-dir external/spider/database \
  --out generation/niches/text-to-sql/evals/spider_dev/qwen4b_base_eval
```

## Result Format

Keep the first report to four numbers:

```text
Model:
Examples:
Execution accuracy:
Invalid SQL rate:
Runtime:
```
