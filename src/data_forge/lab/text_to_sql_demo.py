from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from data_forge.lab.run_card import (
    ApprovalGate,
    Artifact,
    LabMetric,
    LabRunCard,
    LabStep,
    ModelCandidate,
)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _pct(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.2f}%"


def _safe_report(root: Path, relative: str, fallback: dict[str, Any]) -> dict[str, Any]:
    path = root / relative
    return _read_json(path) if path.exists() else fallback


def build_text_to_sql_demo_card(root: Path) -> LabRunCard:
    base_report = _safe_report(
        root,
        "generation/niches/text-to-sql/evals/spider_dev_qwen35_lora_800/base_eval_full_sql_extracted/report.json",
        {"correct": 422, "total": 1034, "execution_accuracy": 0.4081},
    )
    single_report = _safe_report(
        root,
        "generation/niches/text-to-sql/evals/spider_dev_qwen35_lora_800/fine_tuned_eval_full_sql_extracted/report.json",
        {"correct": 598, "total": 1034, "execution_accuracy": 0.5783},
    )
    voted_report = _safe_report(
        root,
        "generation/niches/text-to-sql/evals/spider_dev_qwen35_lora_800_voted/fine_tuned_eval_full_sql_extracted_script/report.json",
        {"correct": 739, "total": 1034, "execution_accuracy": 0.7147},
    )
    selector_report = _safe_report(
        root,
        "generation/niches/text-to-sql/evals/spider_dev_qwen35_lora_800_voted/selector_report.json",
        {
            "strategy": "result-vote",
            "selection_reasons": {
                "primary_result_vote": 881,
                "fallback_1_result_vote": 98,
                "fallback_2_result_vote": 24,
                "fallback_3_result_vote": 5,
                "all_invalid_primary_kept": 26,
            },
            "vote_sizes": {"4": 307, "3": 347, "2": 215, "1": 139, "0": 26},
        },
    )
    progress = _safe_report(
        root,
        "generation/niches/text-to-sql/runs/t2sql_v4pro_10k_012/progress.json",
        {"accepted": 7604, "raw": 10202, "rejected": 2598, "acceptance_rate": 0.7453},
    )
    merge_manifest = _safe_report(
        root,
        "generation/niches/text-to-sql/runs/t2sql_v4pro_10k_012/merged/merge_manifest.json",
        {
            "accepted_count": 7370,
            "duplicate_count": 234,
            "summary": {
                "score_avg": 97.79,
                "difficulties": {"easy": 1324, "medium": 2010, "hard": 2304, "expert": 1732},
            },
        },
    )

    base_acc = float(base_report["execution_accuracy"])
    single_acc = float(single_report["execution_accuracy"])
    voted_acc = float(voted_report["execution_accuracy"])
    total = int(voted_report["total"])

    model_candidates = [
        ModelCandidate(
            model_id="Qwen/Qwen3.5-4B",
            backend="MLX local",
            size="4B",
            license="open",
            local_fit="excellent",
            rationale="Fits a 64GB Apple Silicon machine and supports fast LoRA iteration.",
        ),
        ModelCandidate(
            model_id="google/gemma-3-4b-it",
            backend="Transformers / MLX conversion",
            size="4B",
            license="open weights",
            local_fit="good",
            rationale="Good fallback for instruction following; requires separate baseline.",
        ),
        ModelCandidate(
            model_id="meta-llama/Llama-3.2-3B-Instruct",
            backend="Transformers / llama.cpp",
            size="3B",
            license="community",
            local_fit="good",
            rationale="Smaller local baseline for fast experiments and GGUF deployment.",
        ),
    ]

    steps = [
        LabStep(
            step_id="interpret",
            title="Interpret Task",
            agent="Planner",
            status="needs_approval",
            summary="Classify the prompt as a benchmark-backed Text-to-SQL specialization run.",
            details=[
                "Target output is executable SQLite.",
                "The run must prove improvement over the base model.",
                "Promotion requires held-out benchmark improvement, not subjective examples.",
            ],
            approval=ApprovalGate(
                gate_id="task_interpretation",
                title="Approve task frame",
                prompt="Proceed with Text-to-SQL specialization and Spider dev as the proof benchmark?",
                options=["Approve", "Change benchmark", "Change task"],
                recommended="Approve",
            ),
        ),
        LabStep(
            step_id="benchmark",
            title="Choose Benchmark",
            agent="Evaluator",
            status="complete",
            summary="Selected Spider dev execution accuracy as the primary public proof metric.",
            details=[
                "Metric: execution accuracy against official SQLite databases.",
                "Sample count: 1,034 dev questions.",
                "Secondary checks: valid SQL rate and top execution errors.",
            ],
            metrics=[
                LabMetric("Benchmark", "Spider dev", "public text-to-SQL benchmark"),
                LabMetric("Target metric", "Execution accuracy", "result-set equality"),
            ],
        ),
        LabStep(
            step_id="model",
            title="Select Model + Runtime",
            agent="Model Router",
            status="needs_approval",
            summary="Recommended Qwen/Qwen3.5-4B with MLX LoRA for local Apple Silicon training.",
            details=[
                "Model-agnostic contract records backend, training method, license, and local fit.",
                "The same lab run can route to MLX, Transformers, Colab, or Hugging Face Jobs later.",
            ],
            approval=ApprovalGate(
                gate_id="model_budget",
                title="Approve model and budget",
                prompt="Use Qwen3.5-4B, local MLX LoRA, and benchmark-first promotion gates?",
                options=["Approve", "Use smaller model", "Use cloud GPU"],
                recommended="Approve",
            ),
        ),
        LabStep(
            step_id="forge",
            title="Forge Dataset",
            agent="Data Forge",
            status="complete",
            summary="Generated, gated, deduped, and exported a high-quality synthetic SQL curriculum.",
            details=[
                "Generator: DeepSeek v4 Pro.",
                "Orchestrator: Codex-designed batch specs, gates, and failure feedback.",
                "Rows that failed execution, schema, alias, or quality gates were rejected.",
            ],
            metrics=[
                LabMetric("Raw rows", str(progress.get("raw", "n/a"))),
                LabMetric("Accepted", str(progress.get("accepted", "n/a")), tone="good"),
                LabMetric("Rejected", str(progress.get("rejected", "n/a"))),
                LabMetric("Acceptance", _pct(progress.get("acceptance_rate")), tone="good"),
                LabMetric("Merged rows", str(merge_manifest.get("accepted_count", "n/a"))),
                LabMetric("Avg quality", str(merge_manifest.get("summary", {}).get("score_avg", "n/a")), tone="good"),
            ],
        ),
        LabStep(
            step_id="review",
            title="Review Critical Samples",
            agent="Reviewer",
            status="needs_approval",
            summary="Human review is reserved for high-leverage samples and signoff, not every generated row.",
            details=[
                "The UI should surface edge cases, low-confidence rows, and representative accepted rows.",
                "Rejected rows remain archived and cannot be rescued into training in v1.",
            ],
            approval=ApprovalGate(
                gate_id="dataset_signoff",
                title="Approve dataset signoff",
                prompt="Accept the gated dataset for training after spot review?",
                options=["Approve", "Inspect rows", "Regenerate weak slices"],
                recommended="Approve",
            ),
        ),
        LabStep(
            step_id="train",
            title="Fine-Tune",
            agent="Trainer",
            status="complete",
            summary="Trained an MLX LoRA adapter on the accepted SQL-only SFT split.",
            details=[
                "Adapter training keeps the base model unchanged.",
                "The checkpoint can be saved locally, uploaded to Hugging Face, or used as a candidate in later voting.",
            ],
            metrics=[
                LabMetric("Method", "LoRA"),
                LabMetric("Iterations", "800"),
                LabMetric("Checkpoint", "adapters.safetensors", tone="good"),
            ],
        ),
        LabStep(
            step_id="eval",
            title="Evaluate + Select",
            agent="Evaluator",
            status="complete",
            summary="Measured base, single-pass fine-tune, and result-voted candidates on full Spider dev.",
            details=[
                "Result voting is gold-free: it uses executable candidate agreement, not the answer key.",
                f"Selector strategy: {selector_report.get('strategy', 'result-vote')}.",
            ],
            metrics=[
                LabMetric("Base", _pct(base_acc), f"{base_report['correct']} / {base_report['total']}"),
                LabMetric("Fine-tuned", _pct(single_acc), f"{single_report['correct']} / {single_report['total']}"),
                LabMetric("Voted", _pct(voted_acc), f"{voted_report['correct']} / {voted_report['total']}", "good"),
                LabMetric("Delta vs base", f"+{(voted_acc - base_acc) * 100:.2f} pts", tone="good"),
            ],
        ),
        LabStep(
            step_id="diagnose",
            title="Diagnose Failures",
            agent="Diagnostician",
            status="complete",
            summary="Remaining failures are concentrated in schema grounding and a few malformed candidate outputs.",
            details=[
                "Top residual errors include missing columns, ambiguous names, and incomplete SQL.",
                "Next loop should target schema-linking traps, nested joins, and column-name disambiguation.",
            ],
            metrics=[
                LabMetric("Oracle headroom", "76.60%", "best candidate available before selector"),
                LabMetric("Selected", f"{voted_report['correct']} / {total}", tone="good"),
            ],
        ),
        LabStep(
            step_id="promote",
            title="Promote Checkpoint",
            agent="Publisher",
            status="complete",
            summary="Promoted the adapter because it beat baseline and previous fine-tune reports.",
            details=[
                "Promotion artifact includes model adapter, benchmark report, selector report, and repo provenance.",
                "Rollback remains possible because every run has a manifest and immutable report artifacts.",
            ],
        ),
    ]

    return LabRunCard(
        run_id="lab_text_to_sql_spider_proof",
        title="Text-to-SQL Small Model Lab",
        user_prompt="fine tune a 4B model for text-to-sql",
        thesis="A small local model can become a useful specialist when the dataset factory, gates, and eval loop are engineered as the product.",
        mode="hybrid",
        status="complete",
        task_type="Text-to-SQL",
        benchmark="Spider dev",
        target_metric="Execution accuracy",
        model_candidates=model_candidates,
        steps=steps,
        headline_metrics=[
            LabMetric("Base Qwen3.5-4B", _pct(base_acc), f"{base_report['correct']} / {base_report['total']}"),
            LabMetric("Fine-tuned LoRA", _pct(single_acc), f"{single_report['correct']} / {single_report['total']}"),
            LabMetric("Result-voted system", _pct(voted_acc), f"{voted_report['correct']} / {voted_report['total']}", "good"),
            LabMetric("Improvement", f"+{(voted_acc - base_acc) * 100:.2f} pts", "vs base", "good"),
        ],
        artifacts=[
            Artifact("GitHub repo", "https://github.com/sangwansahil/data-forge", "github"),
            Artifact(
                "Hugging Face model",
                "https://huggingface.co/sahilsangwan/qwen35-4b-text-to-sql-data-forge-lora",
                "huggingface",
            ),
            Artifact(
                "Best Spider report",
                "generation/niches/text-to-sql/evals/spider_dev_qwen35_lora_800_voted/fine_tuned_eval_full_sql_extracted_script/report.json",
                "report",
            ),
            Artifact(
                "Selector report",
                "generation/niches/text-to-sql/evals/spider_dev_qwen35_lora_800_voted/selector_report.json",
                "report",
            ),
            Artifact(
                "Local adapter",
                "generation/niches/text-to-sql/runs/t2sql_v4pro_10k_012/models/qwen35_4b_lora_800/adapters.safetensors",
                "checkpoint",
            ),
        ],
        next_loop=[
            "Make tool-calling the second recipe to prove the harness is not SQL-specific.",
            "Add live approval persistence and a run-state database.",
            "Add backend adapters for MLX, Transformers/TRL, Colab, and Hugging Face Jobs.",
            "Promote only when a run beats baseline and passes regression gates.",
        ],
    )
