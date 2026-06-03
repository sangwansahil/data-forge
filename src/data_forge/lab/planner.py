from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from data_forge.lab.run_card import ApprovalGate, Artifact, LabMetric, LabRunCard, LabStep, ModelCandidate
from data_forge.lab.text_to_sql_demo import build_text_to_sql_demo_card


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48] or "custom-run"


def _run_id(prompt: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"lab_{_slug(prompt)}_{timestamp}"


def _default_models() -> list[ModelCandidate]:
    return [
        ModelCandidate(
            model_id="Qwen/Qwen3.5-4B",
            backend="MLX local",
            size="4B",
            license="open",
            local_fit="excellent",
            rationale="Default local specialist baseline for Apple Silicon LoRA runs.",
        ),
        ModelCandidate(
            model_id="google/gemma-3-4b-it",
            backend="Transformers / Colab",
            size="4B",
            license="open weights",
            local_fit="good",
            rationale="Good instruction-following fallback when MLX support or license fit matters.",
        ),
        ModelCandidate(
            model_id="meta-llama/Llama-3.2-3B-Instruct",
            backend="llama.cpp / Transformers",
            size="3B",
            license="community",
            local_fit="good",
            rationale="Smaller candidate for cheap baselines and GGUF deployment.",
        ),
    ]


def _approval(gate_id: str, title: str, prompt: str, options: Optional[list[str]] = None) -> ApprovalGate:
    choices = options or ["Approve", "Revise", "Stop"]
    return ApprovalGate(gate_id=gate_id, title=title, prompt=prompt, options=choices, recommended=choices[0])


def _generic_steps(task: str, benchmark: str, metric: str) -> list[LabStep]:
    return [
        LabStep(
            step_id="interpret",
            title="Interpret Task",
            agent="Planner",
            status="needs_approval",
            summary=f"Frame this as a {task} specialization run with benchmark-backed promotion.",
            details=[
                "Extract target behavior, expected outputs, data sources, and risk boundaries.",
                "Do not train until an eval plan exists.",
            ],
            approval=_approval("task_interpretation", "Approve task frame", f"Proceed with {task} as the target?"),
        ),
        LabStep(
            step_id="benchmark",
            title="Choose Benchmark",
            agent="Evaluator",
            status="needs_approval",
            summary=f"Use {benchmark} as the primary measurable proof target.",
            details=[
                f"Primary metric: {metric}.",
                "If no public benchmark fits, the lab must create a locked held-out eval before training.",
            ],
            metrics=[LabMetric("Benchmark", benchmark), LabMetric("Metric", metric)],
            approval=_approval("benchmark_plan", "Approve benchmark", f"Use {benchmark} and {metric}?"),
        ),
        LabStep(
            step_id="model",
            title="Select Model + Runtime",
            agent="Model Router",
            status="needs_approval",
            summary="Choose a small base model and training backend before any data generation starts.",
            details=[
                "Model candidates are ranked by local fit, license, trainability, and expected task behavior.",
                "The same plan can route to MLX, Transformers, Colab, or Hugging Face Jobs.",
            ],
            approval=_approval("model_budget", "Approve model and budget", "Use the recommended local small-model plan?"),
        ),
        LabStep(
            step_id="baseline",
            title="Run Baseline",
            agent="Evaluator",
            status="waiting",
            summary="Measure the unmodified base model before training.",
            details=["Promotion requires beating this baseline on the same locked eval."],
        ),
        LabStep(
            step_id="forge",
            title="Forge Dataset",
            agent="Data Forge",
            status="waiting",
            summary="Collect or generate candidate rows, then apply deterministic gates and rubric scoring.",
            details=[
                "Generator choice is configurable; DeepSeek is one cheap option, not a hard dependency.",
                "Accepted, rejected, and review-pending rows are tracked separately.",
            ],
        ),
        LabStep(
            step_id="review",
            title="Review Critical Samples",
            agent="Reviewer",
            status="needs_approval",
            summary="Surface representative rows, low-confidence rows, and gate edge cases for human signoff.",
            details=["Manual review rejects rows; it does not silently rescue auto-rejected rows."],
            approval=_approval("dataset_signoff", "Approve dataset signoff", "Use approved rows for training?"),
        ),
        LabStep(
            step_id="train",
            title="Fine-Tune",
            agent="Trainer",
            status="waiting",
            summary="Run the selected local or cloud training backend and save checkpoints with manifests.",
        ),
        LabStep(
            step_id="eval",
            title="Evaluate",
            agent="Evaluator",
            status="waiting",
            summary="Compare the candidate checkpoint to baseline and previous best on the locked eval.",
        ),
        LabStep(
            step_id="diagnose",
            title="Diagnose Failures",
            agent="Diagnostician",
            status="waiting",
            summary="Convert residual errors into the next targeted data curriculum.",
        ),
        LabStep(
            step_id="promote",
            title="Promote or Roll Back",
            agent="Publisher",
            status="waiting",
            summary="Promote only if the checkpoint beats baseline and passes regression checks.",
        ),
    ]


def plan_lab_run(prompt: str, root: Path) -> LabRunCard:
    lower = prompt.lower()
    if "sql" in lower:
        card = build_text_to_sql_demo_card(root)
        return replace(card, run_id=_run_id(prompt), user_prompt=prompt, mode="live", status="ready")

    if "tool" in lower or "function" in lower:
        return LabRunCard(
            run_id=_run_id(prompt),
            title="Tool-Calling Small Model Lab",
            user_prompt=prompt,
            thesis="A small model can become a strong tool caller when schemas, negative cases, and executable validation drive the data loop.",
            mode="live",
            status="ready",
            task_type="Tool calling",
            benchmark="BFCL-style function calling eval",
            target_metric="Tool selection + argument accuracy",
            model_candidates=_default_models(),
            steps=_generic_steps("tool-calling", "BFCL", "AST/function-call accuracy"),
            headline_metrics=[
                LabMetric("Baseline", "pending"),
                LabMetric("Fine-tune", "pending"),
                LabMetric("Valid calls", "pending"),
                LabMetric("Promotion", "locked", "requires eval improvement"),
            ],
            artifacts=[],
            next_loop=[
                "Download or define the BFCL subset.",
                "Generate tool schemas, positive calls, negative no-call rows, and parallel-call cases.",
                "Train only after baseline and locked eval are saved.",
            ],
        )

    task = "custom-domain"
    return LabRunCard(
        run_id=_run_id(prompt),
        title="Custom Small Model Lab",
        user_prompt=prompt,
        thesis="Data Forge Lab will turn the prompt into a benchmark-backed adaptation plan before training.",
        mode="live",
        status="ready",
        task_type=task,
        benchmark="locked held-out eval",
        target_metric="task-specific score",
        model_candidates=_default_models(),
        steps=_generic_steps(task, "locked held-out eval", "task-specific score"),
        headline_metrics=[
            LabMetric("Task", "planned"),
            LabMetric("Benchmark", "pending"),
            LabMetric("Baseline", "pending"),
            LabMetric("Promotion", "locked", "requires eval improvement"),
        ],
        artifacts=[],
        next_loop=[
            "Resolve task type and benchmark.",
            "Create a minimal baseline eval before any data generation.",
            "Choose the smallest local model that can plausibly learn the target behavior.",
        ],
    )
