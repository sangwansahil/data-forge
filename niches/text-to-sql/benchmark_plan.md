# Text-to-SQL Benchmark Plan

## Phase 1: local proof

Train on accepted synthetic rows only.

Evaluate:

- Base 4B model.
- Fine-tuned 4B model.
- Same prompt, same decoding, same harness.

Metrics:

- Execution accuracy.
- Exact match where benchmark supports it.
- Invalid SQL rate.
- Timeout rate.
- Error category distribution.

## Phase 2: public proof

Run official or commonly accepted scripts for:

- Spider 1.0 dev.
- BIRD dev.
- Spider 2.0 Lite where feasible.
- LiveSQLBench when the agent harness is mature.

## Phase 3: scale decision

Scale generation only when:

- Synthetic held-out accuracy improves over the base model.
- Benchmark dev accuracy improves over the base model.
- Rejection reasons are stable and understandable.
- More data still helps on the validation curve.

## Reporting template

```text
Model: qwen3.5-4b + LoRA
Accepted rows: 5,000
Raw rows generated: 18,400
Acceptance rate: 27.2%
Generator: DeepSeek
Judge threshold: 85
Benchmark: BIRD dev
Base execution accuracy: ...
Fine-tuned execution accuracy: ...
Invalid SQL rate: ...
Run command: ...
```
