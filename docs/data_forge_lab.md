# Data Forge Lab

Data Forge Lab is the agentic product layer on top of `data-forge`.

The end product is a local-first AI lab console for small-model specialization. A user writes a task prompt, approves a few critical decisions, and the lab runs a closed experiment loop until it can promote a benchmarked checkpoint or explain why the run failed.

## Product Promise

```text
User prompt
  -> task interpretation
  -> benchmark choice
  -> model/runtime choice
  -> baseline eval
  -> data forge
  -> quality gates
  -> review/signoff
  -> fine-tune
  -> eval
  -> diagnose
  -> targeted next data loop
  -> promote or roll back
```

The product is not a collection of training scripts. The product is the experiment harness: plans, manifests, approvals, data gates, evals, diagnosis, and promotion control.

## User Experience

The user should only need to:

1. Write a prompt such as `fine tune a 4B model for text-to-sql`.
2. Approve critical decisions in visual blocks.
3. Inspect a small number of representative rows or failure examples.
4. Receive a model checkpoint with reports.
5. Save locally or push to Hugging Face.

The UI should stay focused on 3-5 metrics at a time. Training logs, row archives, and detailed reports remain available as artifacts, but they should not dominate the main path.

## Model-Agnostic Design

The lab treats models and runtimes as replaceable backends.

Model cards should capture:

- model id
- backend
- trainability
- expected local fit
- license
- context length
- recommended training method

Initial backend targets:

- MLX on Apple Silicon
- Transformers / TRL
- Colab
- Hugging Face Jobs
- llama.cpp / GGUF export
- Ollama inference-only evals

## Approval Gates

Approvals are reserved for decisions where human intent matters:

- task interpretation
- benchmark/eval plan
- model and budget
- dataset signoff
- final publish/save

Everything else should be automated and reproducible.

## MVP Demo

The first demo is a static/hybrid replay of the completed Text-to-SQL proof run:

- Base model: `Qwen/Qwen3.5-4B`
- Fine-tuning method: MLX LoRA
- Generator: DeepSeek v4 Pro
- Orchestrator: Codex-designed generation specs, gates, and failure loops
- Benchmark: Spider dev execution accuracy
- Base result: 40.81%
- Fine-tuned single-pass result: 57.83%
- Result-voted system: 71.47%

Run locally:

```bash
python3 scripts/build_lab_demo.py
python3 -m http.server 8765 --directory apps/lab-ui
```

Then open:

```text
http://localhost:8765
```

The static demo can later be deployed unchanged to Vercel, GitHub Pages, or a Hugging Face Space.

## Live Harness Roadmap

1. Persist lab run state as JSON manifests.
2. Add backend adapters for local MLX and Transformers training.
3. Add recipe registry for Text-to-SQL, tool calling, classification, and extraction.
4. Add a review queue that surfaces only high-leverage samples.
5. Add automatic failure taxonomy and targeted data generation.
6. Add promotion gates that compare candidate checkpoints against baseline and previous best.
7. Add one-click export to local disk and Hugging Face.

## Rule

No checkpoint is promoted unless it beats the baseline on the chosen eval and passes regression checks.
