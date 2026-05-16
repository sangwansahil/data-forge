# Qwen 4B LoRA Fine-Tune Recipe

This is the intended first training path once enough rows pass the gates.

## Dataset export

```bash
python3 scripts/export_text_to_sql_sft.py \
  generation/accepted/pilot_001.jsonl \
  --out generation/accepted/pilot_001_sft.jsonl
```

## Training shape

- Base model: Qwen3.5-4B or another permissive 2B-4B model.
- Method: QLoRA/LoRA SFT.
- First dataset size: 5,000 accepted rows.
- Serious dataset size: 30,000-100,000 accepted rows.
- Keep a synthetic held-out split by schema, not by row, so the model cannot memorize table layouts.

## Eval discipline

Use the exact same inference scaffold for:

- Base model.
- Fine-tuned model.
- Any closed model comparison.

Track:

- Execution accuracy.
- Invalid SQL rate.
- Mean attempts per solved task if using retries.
- Token cost and latency.
- Error clusters.

## Important

Do not add benchmark rows to training data. The proof of work is the generalization gap between base and fine-tuned model on public evals.
