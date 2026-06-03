window.DATA_FORGE_DEMO_RUN = {
  "artifacts": [
    {
      "kind": "github",
      "label": "GitHub repo",
      "uri": "https://github.com/sangwansahil/data-forge"
    },
    {
      "kind": "huggingface",
      "label": "Hugging Face model",
      "uri": "https://huggingface.co/sahilsangwan/qwen35-4b-text-to-sql-data-forge-lora"
    },
    {
      "kind": "report",
      "label": "Best Spider report",
      "uri": "generation/niches/text-to-sql/evals/spider_dev_qwen35_lora_800_voted/fine_tuned_eval_full_sql_extracted_script/report.json"
    },
    {
      "kind": "report",
      "label": "Selector report",
      "uri": "generation/niches/text-to-sql/evals/spider_dev_qwen35_lora_800_voted/selector_report.json"
    },
    {
      "kind": "checkpoint",
      "label": "Local adapter",
      "uri": "generation/niches/text-to-sql/runs/t2sql_v4pro_10k_012/models/qwen35_4b_lora_800/adapters.safetensors"
    }
  ],
  "benchmark": "Spider dev",
  "headline_metrics": [
    {
      "detail": "422 / 1034",
      "label": "Base Qwen3.5-4B",
      "tone": "neutral",
      "value": "40.81%"
    },
    {
      "detail": "598 / 1034",
      "label": "Fine-tuned LoRA",
      "tone": "neutral",
      "value": "57.83%"
    },
    {
      "detail": "739 / 1034",
      "label": "Result-voted system",
      "tone": "good",
      "value": "71.47%"
    },
    {
      "detail": "vs base",
      "label": "Improvement",
      "tone": "good",
      "value": "+30.66 pts"
    }
  ],
  "mode": "hybrid",
  "model_candidates": [
    {
      "backend": "MLX local",
      "license": "open",
      "local_fit": "excellent",
      "model_id": "Qwen/Qwen3.5-4B",
      "rationale": "Fits a 64GB Apple Silicon machine and supports fast LoRA iteration.",
      "size": "4B"
    },
    {
      "backend": "Transformers / MLX conversion",
      "license": "open weights",
      "local_fit": "good",
      "model_id": "google/gemma-3-4b-it",
      "rationale": "Good fallback for instruction following; requires separate baseline.",
      "size": "4B"
    },
    {
      "backend": "Transformers / llama.cpp",
      "license": "community",
      "local_fit": "good",
      "model_id": "meta-llama/Llama-3.2-3B-Instruct",
      "rationale": "Smaller local baseline for fast experiments and GGUF deployment.",
      "size": "3B"
    }
  ],
  "next_loop": [
    "Make tool-calling the second recipe to prove the harness is not SQL-specific.",
    "Add live approval persistence and a run-state database.",
    "Add backend adapters for MLX, Transformers/TRL, Colab, and Hugging Face Jobs.",
    "Promote only when a run beats baseline and passes regression gates."
  ],
  "run_id": "lab_text_to_sql_spider_proof",
  "status": "complete",
  "steps": [
    {
      "agent": "Planner",
      "approval": {
        "gate_id": "task_interpretation",
        "options": [
          "Approve",
          "Change benchmark",
          "Change task"
        ],
        "prompt": "Proceed with Text-to-SQL specialization and Spider dev as the proof benchmark?",
        "recommended": "Approve",
        "required": true,
        "title": "Approve task frame"
      },
      "details": [
        "Target output is executable SQLite.",
        "The run must prove improvement over the base model.",
        "Promotion requires held-out benchmark improvement, not subjective examples."
      ],
      "metrics": [],
      "status": "needs_approval",
      "step_id": "interpret",
      "summary": "Classify the prompt as a benchmark-backed Text-to-SQL specialization run.",
      "title": "Interpret Task"
    },
    {
      "agent": "Evaluator",
      "approval": null,
      "details": [
        "Metric: execution accuracy against official SQLite databases.",
        "Sample count: 1,034 dev questions.",
        "Secondary checks: valid SQL rate and top execution errors."
      ],
      "metrics": [
        {
          "detail": "public text-to-SQL benchmark",
          "label": "Benchmark",
          "tone": "neutral",
          "value": "Spider dev"
        },
        {
          "detail": "result-set equality",
          "label": "Target metric",
          "tone": "neutral",
          "value": "Execution accuracy"
        }
      ],
      "status": "complete",
      "step_id": "benchmark",
      "summary": "Selected Spider dev execution accuracy as the primary public proof metric.",
      "title": "Choose Benchmark"
    },
    {
      "agent": "Model Router",
      "approval": {
        "gate_id": "model_budget",
        "options": [
          "Approve",
          "Use smaller model",
          "Use cloud GPU"
        ],
        "prompt": "Use Qwen3.5-4B, local MLX LoRA, and benchmark-first promotion gates?",
        "recommended": "Approve",
        "required": true,
        "title": "Approve model and budget"
      },
      "details": [
        "Model-agnostic contract records backend, training method, license, and local fit.",
        "The same lab run can route to MLX, Transformers, Colab, or Hugging Face Jobs later."
      ],
      "metrics": [],
      "status": "needs_approval",
      "step_id": "model",
      "summary": "Recommended Qwen/Qwen3.5-4B with MLX LoRA for local Apple Silicon training.",
      "title": "Select Model + Runtime"
    },
    {
      "agent": "Data Forge",
      "approval": null,
      "details": [
        "Generator: DeepSeek v4 Pro.",
        "Orchestrator: Codex-designed batch specs, gates, and failure feedback.",
        "Rows that failed execution, schema, alias, or quality gates were rejected."
      ],
      "metrics": [
        {
          "detail": "",
          "label": "Raw rows",
          "tone": "neutral",
          "value": "10202"
        },
        {
          "detail": "",
          "label": "Accepted",
          "tone": "good",
          "value": "7604"
        },
        {
          "detail": "",
          "label": "Rejected",
          "tone": "neutral",
          "value": "2598"
        },
        {
          "detail": "",
          "label": "Acceptance",
          "tone": "good",
          "value": "74.53%"
        },
        {
          "detail": "",
          "label": "Merged rows",
          "tone": "neutral",
          "value": "7370"
        },
        {
          "detail": "",
          "label": "Avg quality",
          "tone": "good",
          "value": "97.79"
        }
      ],
      "status": "complete",
      "step_id": "forge",
      "summary": "Generated, gated, deduped, and exported a high-quality synthetic SQL curriculum.",
      "title": "Forge Dataset"
    },
    {
      "agent": "Reviewer",
      "approval": {
        "gate_id": "dataset_signoff",
        "options": [
          "Approve",
          "Inspect rows",
          "Regenerate weak slices"
        ],
        "prompt": "Accept the gated dataset for training after spot review?",
        "recommended": "Approve",
        "required": true,
        "title": "Approve dataset signoff"
      },
      "details": [
        "The UI should surface edge cases, low-confidence rows, and representative accepted rows.",
        "Rejected rows remain archived and cannot be rescued into training in v1."
      ],
      "metrics": [],
      "status": "needs_approval",
      "step_id": "review",
      "summary": "Human review is reserved for high-leverage samples and signoff, not every generated row.",
      "title": "Review Critical Samples"
    },
    {
      "agent": "Trainer",
      "approval": null,
      "details": [
        "Adapter training keeps the base model unchanged.",
        "The checkpoint can be saved locally, uploaded to Hugging Face, or used as a candidate in later voting."
      ],
      "metrics": [
        {
          "detail": "",
          "label": "Method",
          "tone": "neutral",
          "value": "LoRA"
        },
        {
          "detail": "",
          "label": "Iterations",
          "tone": "neutral",
          "value": "800"
        },
        {
          "detail": "",
          "label": "Checkpoint",
          "tone": "good",
          "value": "adapters.safetensors"
        }
      ],
      "status": "complete",
      "step_id": "train",
      "summary": "Trained an MLX LoRA adapter on the accepted SQL-only SFT split.",
      "title": "Fine-Tune"
    },
    {
      "agent": "Evaluator",
      "approval": null,
      "details": [
        "Result voting is gold-free: it uses executable candidate agreement, not the answer key.",
        "Selector strategy: result-vote."
      ],
      "metrics": [
        {
          "detail": "422 / 1034",
          "label": "Base",
          "tone": "neutral",
          "value": "40.81%"
        },
        {
          "detail": "598 / 1034",
          "label": "Fine-tuned",
          "tone": "neutral",
          "value": "57.83%"
        },
        {
          "detail": "739 / 1034",
          "label": "Voted",
          "tone": "good",
          "value": "71.47%"
        },
        {
          "detail": "",
          "label": "Delta vs base",
          "tone": "good",
          "value": "+30.66 pts"
        }
      ],
      "status": "complete",
      "step_id": "eval",
      "summary": "Measured base, single-pass fine-tune, and result-voted candidates on full Spider dev.",
      "title": "Evaluate + Select"
    },
    {
      "agent": "Diagnostician",
      "approval": null,
      "details": [
        "Top residual errors include missing columns, ambiguous names, and incomplete SQL.",
        "Next loop should target schema-linking traps, nested joins, and column-name disambiguation."
      ],
      "metrics": [
        {
          "detail": "best candidate available before selector",
          "label": "Oracle headroom",
          "tone": "neutral",
          "value": "76.60%"
        },
        {
          "detail": "",
          "label": "Selected",
          "tone": "good",
          "value": "739 / 1034"
        }
      ],
      "status": "complete",
      "step_id": "diagnose",
      "summary": "Remaining failures are concentrated in schema grounding and a few malformed candidate outputs.",
      "title": "Diagnose Failures"
    },
    {
      "agent": "Publisher",
      "approval": null,
      "details": [
        "Promotion artifact includes model adapter, benchmark report, selector report, and repo provenance.",
        "Rollback remains possible because every run has a manifest and immutable report artifacts."
      ],
      "metrics": [],
      "status": "complete",
      "step_id": "promote",
      "summary": "Promoted the adapter because it beat baseline and previous fine-tune reports.",
      "title": "Promote Checkpoint"
    }
  ],
  "target_metric": "Execution accuracy",
  "task_type": "Text-to-SQL",
  "thesis": "A small local model can become a useful specialist when the dataset factory, gates, and eval loop are engineered as the product.",
  "title": "Text-to-SQL Small Model Lab",
  "user_prompt": "fine tune a 4B model for text-to-sql"
};
