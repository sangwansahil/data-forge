from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from data_forge.lab.run_card import Artifact, LabMetric, LabRunCard, LabStep
from data_forge.lab.state import LabRunEnvelope, utc_now
from data_forge.niches.tool_calling.eval import evaluate_tool_call_records


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")


def _replace_step(run: LabRunCard, step_id: str, new_step: LabStep) -> LabRunCard:
    return replace(run, steps=[new_step if step.step_id == step_id else step for step in run.steps])


def _append_artifacts(run: LabRunCard, artifacts: list[Artifact]) -> LabRunCard:
    existing = {(artifact.label, artifact.uri) for artifact in run.artifacts}
    merged = list(run.artifacts)
    for artifact in artifacts:
        key = (artifact.label, artifact.uri)
        if key not in existing:
            merged.append(artifact)
    return replace(run, artifacts=merged)


def _replace_headline_metrics(run: LabRunCard, updates: dict[str, LabMetric]) -> LabRunCard:
    labels = set(updates)
    metrics = [updates[metric.label] if metric.label in labels else metric for metric in run.headline_metrics]
    existing = {metric.label for metric in metrics}
    metrics.extend(metric for label, metric in updates.items() if label not in existing)
    return replace(run, headline_metrics=metrics)


def _current_step(envelope: LabRunEnvelope) -> LabStep:
    if envelope.current_step_index < 1 or envelope.current_step_index > len(envelope.run.steps):
        raise ValueError("run has no current executable step")
    return envelope.run.steps[envelope.current_step_index - 1]


def _run_tool_calling_baseline(project_root: Path, run_dir: Path, envelope: LabRunEnvelope) -> LabRunEnvelope:
    fixture = project_root / "niches/tool-calling/examples/eval_cases.jsonl"
    eval_path = run_dir / "tool_calling" / "locked_eval.jsonl"
    predictions_path = run_dir / "tool_calling" / "baseline_predictions.jsonl"
    report_path = run_dir / "tool_calling" / "baseline_report.json"
    results_path = run_dir / "tool_calling" / "baseline_results.jsonl"

    eval_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture, eval_path)
    records = _read_jsonl(eval_path)
    baseline_records = []
    for record in records:
        payload = dict(record)
        payload["predicted_calls"] = []
        baseline_records.append(payload)
    _write_jsonl(predictions_path, baseline_records)
    results, summary = evaluate_tool_call_records(baseline_records)
    _write_json(report_path, summary)
    _write_jsonl(results_path, [result.to_dict() for result in results])

    step = _current_step(envelope)
    completed = replace(
        step,
        status="complete",
        summary="Created a locked BFCL-style seed eval and measured the no-tool baseline.",
        metrics=[
            LabMetric("Eval cases", str(summary["total"])),
            LabMetric("Exact", f"{summary['exact_accuracy'] * 100:.2f}%"),
            LabMetric("Valid", f"{summary['valid_prediction_rate'] * 100:.2f}%"),
            LabMetric("Tool choice", f"{summary['tool_selection_accuracy'] * 100:.2f}%"),
        ],
    )
    run = _replace_step(envelope.run, step.step_id, completed)
    run = _append_artifacts(
        run,
        [
            Artifact("Tool-calling locked eval", str(eval_path.relative_to(project_root)), "dataset"),
            Artifact("Tool-calling baseline report", str(report_path.relative_to(project_root)), "report"),
            Artifact("Tool-calling baseline results", str(results_path.relative_to(project_root)), "report"),
        ],
    )
    run = _replace_headline_metrics(
        run,
        {
            "Baseline": LabMetric(
                "Baseline",
                f"{summary['exact_accuracy'] * 100:.2f}%",
                f"{summary['exact']} / {summary['total']} exact",
            ),
            "Valid calls": LabMetric(
                "Valid calls",
                f"{summary['valid_prediction_rate'] * 100:.2f}%",
                "baseline parser validity",
            ),
        },
    )
    envelope.run = run
    envelope.events.append({"type": "step_completed", "at": utc_now(), "step_id": step.step_id})
    return envelope


def _tool_calling_seed_rows() -> list[dict[str, Any]]:
    return [
        {
            "row_id": "tool_seed_calendar_001",
            "status": "accepted",
            "domain": "calendar",
            "skill": "single_tool_call",
            "instruction": "Schedule a kickoff call with Maya tomorrow at 10:00 for 30 minutes.",
            "expected_calls": [
                {
                    "name": "create_calendar_event",
                    "arguments": {
                        "title": "Kickoff call",
                        "attendee": "Maya",
                        "day": "tomorrow",
                        "time": "10:00",
                        "duration_minutes": 30,
                    },
                }
            ],
            "gate_notes": ["valid JSON", "required args present", "tool is relevant"],
        },
        {
            "row_id": "tool_seed_relevance_001",
            "status": "accepted",
            "domain": "general_qa",
            "skill": "no_tool_relevance",
            "instruction": "Explain why the sky looks blue in two sentences.",
            "expected_calls": [],
            "gate_notes": ["no tool should be called", "relevance gate passes"],
        },
        {
            "row_id": "tool_seed_bad_001",
            "status": "rejected",
            "domain": "crm",
            "skill": "argument_grounding",
            "instruction": "Update Acme to customer.",
            "expected_calls": [{"name": "update_account_stage", "arguments": {"stage": "customer"}}],
            "gate_notes": ["rejected: missing account identifier argument"],
        },
    ]


def _run_tool_calling_forge(project_root: Path, run_dir: Path, envelope: LabRunEnvelope) -> LabRunEnvelope:
    data_dir = run_dir / "tool_calling"
    plan_path = data_dir / "data_plan.json"
    seed_rows_path = data_dir / "seed_rows.jsonl"
    quality_path = data_dir / "quality_report.json"
    seed_rows = _tool_calling_seed_rows()
    accepted = [row for row in seed_rows if row["status"] == "accepted"]
    rejected = [row for row in seed_rows if row["status"] == "rejected"]
    plan = {
        "target": "BFCL-style tool calling",
        "generator": "configurable; DeepSeek or any OpenAI-compatible model",
        "skills": [
            "single_tool_call",
            "multi_tool_call",
            "parallel_tool_call",
            "argument_grounding",
            "no_tool_relevance",
        ],
        "gates": [
            "valid JSON",
            "known tool name",
            "required argument coverage",
            "argument type match",
            "negative relevance correctness",
            "duplicate intent fingerprint",
        ],
    }
    quality = {
        "rows": len(seed_rows),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "acceptance_rate": round(len(accepted) / len(seed_rows), 4),
        "top_rejection_reasons": {"missing account identifier argument": 1},
    }
    _write_json(plan_path, plan)
    _write_jsonl(seed_rows_path, seed_rows)
    _write_json(quality_path, quality)

    step = _current_step(envelope)
    completed = replace(
        step,
        status="complete",
        summary="Created the first tool-calling data plan, gates, and seed review rows.",
        metrics=[
            LabMetric("Seed rows", str(len(seed_rows))),
            LabMetric("Accepted", str(len(accepted)), tone="good"),
            LabMetric("Rejected", str(len(rejected))),
            LabMetric("Acceptance", f"{quality['acceptance_rate'] * 100:.2f}%"),
        ],
    )
    run = _replace_step(envelope.run, step.step_id, completed)
    run = _append_artifacts(
        run,
        [
            Artifact("Tool-calling data plan", str(plan_path.relative_to(project_root)), "report"),
            Artifact("Tool-calling seed rows", str(seed_rows_path.relative_to(project_root)), "dataset"),
            Artifact("Tool-calling quality report", str(quality_path.relative_to(project_root)), "report"),
        ],
    )
    envelope.run = run
    envelope.events.append({"type": "step_completed", "at": utc_now(), "step_id": step.step_id})
    return envelope


def run_current_step(*, project_root: Path, run_dir: Path, envelope: LabRunEnvelope) -> LabRunEnvelope:
    step = _current_step(envelope)
    if step.approval and step.approval.gate_id not in envelope.approved_gates:
        raise ValueError(f"approval required before running step: {step.approval.gate_id}")
    if step.status == "complete":
        return envelope
    if envelope.run.task_type == "Tool calling" and step.step_id == "baseline":
        return _run_tool_calling_baseline(project_root, run_dir, envelope)
    if envelope.run.task_type == "Tool calling" and step.step_id == "forge":
        return _run_tool_calling_forge(project_root, run_dir, envelope)
    blocked = replace(
        step,
        status="blocked",
        summary=step.summary + " Runner is not implemented yet for this step.",
        details=[*step.details, "This is the next backend integration point for Data Forge Lab."],
    )
    envelope.run = _replace_step(envelope.run, step.step_id, blocked)
    envelope.events.append(
        {"type": "step_blocked", "at": utc_now(), "step_id": step.step_id, "reason": "runner not implemented"}
    )
    return envelope
