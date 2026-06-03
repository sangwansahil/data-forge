from __future__ import annotations

import json
import os
import shutil
import tarfile
from io import BytesIO
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


def _tool_calling_dir(run_dir: Path) -> Path:
    return run_dir / "tool_calling"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def _add_json_to_tar(tar: tarfile.TarFile, arcname: str, payload: dict[str, Any]) -> None:
    content = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    info = tarfile.TarInfo(arcname)
    info.size = len(content)
    tar.addfile(info, BytesIO(content))


def _write_checkpoint_package(
    *,
    project_root: Path,
    data_dir: Path,
    envelope: LabRunEnvelope,
    promotion_path: Path,
) -> tuple[Path, Path]:
    checkpoint_dir = data_dir / "checkpoints" / "candidate_0001"
    package_path = data_dir / "checkpoint_package.tar.gz"
    package_manifest_path = data_dir / "checkpoint_package_manifest.json"
    files = [
        checkpoint_dir / "checkpoint_manifest.json",
        checkpoint_dir / "README.md",
        data_dir / "training_manifest.json",
        data_dir / "candidate_eval_report.json",
        data_dir / "diagnosis.json",
        promotion_path,
    ]
    package_manifest = {
        "package_type": "data_forge_lab_checkpoint",
        "run_id": envelope.run.run_id,
        "task_type": envelope.run.task_type,
        "benchmark": envelope.run.benchmark,
        "created_at": utc_now(),
        "checkpoint_dir": str(checkpoint_dir.relative_to(project_root)),
        "package_path": str(package_path.relative_to(project_root)),
        "files": [str(path.relative_to(project_root)) for path in files],
        "huggingface_upload": {
            "enabled": False,
            "reason": "dry-run checkpoint contract has no model weights to publish",
        },
    }
    _write_json(package_manifest_path, package_manifest)

    with tarfile.open(package_path, "w:gz") as tar:
        for path in files:
            tar.add(path, arcname=str(path.relative_to(data_dir)))
        tar.add(package_manifest_path, arcname="checkpoint_package_manifest.json")
        _add_json_to_tar(tar, "lab_run_snapshot.json", envelope.to_dict())
    return package_path, package_manifest_path


def _run_tool_calling_train(project_root: Path, run_dir: Path, envelope: LabRunEnvelope) -> LabRunEnvelope:
    data_dir = _tool_calling_dir(run_dir)
    seed_rows_path = data_dir / "seed_rows.jsonl"
    if not seed_rows_path.exists():
        raise ValueError("seed rows are required before training")
    rows = _read_jsonl(seed_rows_path)
    accepted_rows = [row for row in rows if row.get("status") == "accepted"]
    checkpoint_dir = data_dir / "checkpoints" / "candidate_0001"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    backend = os.environ.get("DATA_FORGE_LAB_TRAIN_BACKEND", "dry-run")
    base_model = envelope.run.model_candidates[0].model_id if envelope.run.model_candidates else "bring-your-own-model"
    manifest = {
        "checkpoint_id": f"{envelope.run.run_id}_candidate_0001",
        "status": "dry_run_contract",
        "backend": backend,
        "base_model": base_model,
        "task_type": envelope.run.task_type,
        "training_rows": len(accepted_rows),
        "source_dataset": str(seed_rows_path.relative_to(project_root)),
        "created_at": utc_now(),
        "save_targets": ["local", "huggingface"],
        "notes": [
            "This MVP writes a checkpoint handoff contract, not model weights.",
            "A real backend adapter must replace dry-run before promotion can claim model improvement.",
        ],
    }
    training_manifest_path = data_dir / "training_manifest.json"
    checkpoint_manifest_path = checkpoint_dir / "checkpoint_manifest.json"
    checkpoint_readme_path = checkpoint_dir / "README.md"
    _write_json(training_manifest_path, manifest)
    _write_json(checkpoint_manifest_path, manifest)
    checkpoint_readme_path.write_text(
        "\n".join(
            [
                "# Data Forge Lab checkpoint handoff",
                "",
                "This directory is a model-agnostic checkpoint contract for the Lab runner.",
                "It is intentionally marked `dry_run_contract` until a real training backend writes weights.",
                "",
                f"- Base model: `{base_model}`",
                f"- Backend: `{backend}`",
                f"- Training rows: `{len(accepted_rows)}`",
                "",
            ]
        )
    )

    step = _current_step(envelope)
    completed = replace(
        step,
        status="complete",
        summary="Prepared a model-agnostic checkpoint handoff contract for the selected training backend.",
        details=[
            "The dry-run backend proves artifact plumbing without fabricating model weights.",
            "Real backends will write adapter weights into the same checkpoint contract.",
        ],
        metrics=[
            LabMetric("Backend", backend),
            LabMetric("Rows", str(len(accepted_rows))),
            LabMetric("Checkpoint", "contract"),
            LabMetric("Save targets", "local + HF"),
        ],
    )
    run = _replace_step(envelope.run, step.step_id, completed)
    run = _append_artifacts(
        run,
        [
            Artifact("Training manifest", str(training_manifest_path.relative_to(project_root)), "report"),
            Artifact("Checkpoint contract", str(checkpoint_manifest_path.relative_to(project_root)), "checkpoint"),
        ],
    )
    run = _replace_headline_metrics(
        run,
        {
            "Fine-tune": LabMetric(
                "Fine-tune",
                "contract",
                "dry-run backend; weights not generated",
                tone="warn",
            )
        },
    )
    envelope.run = run
    envelope.events.append({"type": "step_completed", "at": utc_now(), "step_id": step.step_id})
    return envelope


def _run_tool_calling_eval(project_root: Path, run_dir: Path, envelope: LabRunEnvelope) -> LabRunEnvelope:
    data_dir = _tool_calling_dir(run_dir)
    baseline_report_path = data_dir / "baseline_report.json"
    checkpoint_manifest_path = data_dir / "checkpoints" / "candidate_0001" / "checkpoint_manifest.json"
    if not baseline_report_path.exists() or not checkpoint_manifest_path.exists():
        raise ValueError("baseline report and checkpoint manifest are required before eval")
    baseline = _load_json(baseline_report_path)
    checkpoint = _load_json(checkpoint_manifest_path)
    report = {
        "benchmark": envelope.run.benchmark,
        "metric": envelope.run.target_metric,
        "sample_count": baseline["total"],
        "baseline_exact_accuracy": baseline["exact_accuracy"],
        "candidate_exact_accuracy": None,
        "candidate_status": checkpoint["status"],
        "promotion_ready": False,
        "reason": "dry-run checkpoint contract has no model weights to evaluate",
        "created_at": utc_now(),
    }
    report_path = data_dir / "candidate_eval_report.json"
    _write_json(report_path, report)

    step = _current_step(envelope)
    completed = replace(
        step,
        status="complete",
        summary="Recorded the eval contract and blocked metric claims until a real checkpoint exists.",
        details=[
            "The Lab keeps the baseline metric visible.",
            "No candidate accuracy is claimed for a dry-run checkpoint.",
        ],
        metrics=[
            LabMetric("Baseline", f"{baseline['exact_accuracy'] * 100:.2f}%"),
            LabMetric("Candidate", "not run", tone="warn"),
            LabMetric("Samples", str(baseline["total"])),
            LabMetric("Promotion", "blocked", tone="warn"),
        ],
    )
    run = _replace_step(envelope.run, step.step_id, completed)
    run = _append_artifacts(run, [Artifact("Candidate eval report", str(report_path.relative_to(project_root)), "report")])
    envelope.run = run
    envelope.events.append({"type": "step_completed", "at": utc_now(), "step_id": step.step_id})
    return envelope


def _run_tool_calling_diagnose(project_root: Path, run_dir: Path, envelope: LabRunEnvelope) -> LabRunEnvelope:
    data_dir = _tool_calling_dir(run_dir)
    quality_path = data_dir / "quality_report.json"
    eval_path = data_dir / "candidate_eval_report.json"
    quality = _load_json(quality_path)
    eval_report = _load_json(eval_path)
    diagnosis = {
        "status": "next_loop_ready",
        "top_findings": [
            "Replace dry-run backend with MLX or Transformers adapter execution.",
            "Expand BFCL-style locked eval before spending generator budget.",
            "Add rejected-row review UI so humans can inspect failure modes before training.",
        ],
        "quality_signal": quality,
        "eval_signal": eval_report,
        "created_at": utc_now(),
    }
    diagnosis_path = data_dir / "diagnosis.json"
    _write_json(diagnosis_path, diagnosis)

    step = _current_step(envelope)
    completed = replace(
        step,
        status="complete",
        summary="Converted the current run state into the next implementation loop.",
        metrics=[
            LabMetric("Findings", str(len(diagnosis["top_findings"]))),
            LabMetric("Next loop", "backend adapter"),
            LabMetric("Risk", "no weights yet", tone="warn"),
        ],
    )
    run = _replace_step(envelope.run, step.step_id, completed)
    run = _append_artifacts(run, [Artifact("Diagnosis report", str(diagnosis_path.relative_to(project_root)), "report")])
    envelope.run = run
    envelope.events.append({"type": "step_completed", "at": utc_now(), "step_id": step.step_id})
    return envelope


def _run_tool_calling_promote(project_root: Path, run_dir: Path, envelope: LabRunEnvelope) -> LabRunEnvelope:
    data_dir = _tool_calling_dir(run_dir)
    eval_report = _load_json(data_dir / "candidate_eval_report.json")
    promotion = {
        "decision": "do_not_promote",
        "reason": eval_report["reason"],
        "can_save_local": True,
        "can_push_huggingface": False,
        "checkpoint_uri": str((data_dir / "checkpoints" / "candidate_0001").relative_to(project_root)),
        "created_at": utc_now(),
        "requirements_to_promote": [
            "A real backend writes adapter/model weights.",
            "Candidate beats baseline on the locked eval.",
            "Regression checks pass.",
        ],
    }
    promotion_path = data_dir / "promotion_decision.json"
    _write_json(promotion_path, promotion)
    package_path, package_manifest_path = _write_checkpoint_package(
        project_root=project_root,
        data_dir=data_dir,
        envelope=envelope,
        promotion_path=promotion_path,
    )

    step = _current_step(envelope)
    completed = replace(
        step,
        status="complete",
        summary="Saved the checkpoint contract locally and withheld promotion because no real weights exist yet.",
        details=[
            "The Lab can hand off local artifacts now.",
            "Hugging Face publishing remains disabled until a real checkpoint passes eval.",
        ],
        metrics=[
            LabMetric("Decision", "no promote", tone="warn"),
            LabMetric("Local save", "ready", tone="good"),
            LabMetric("HF push", "locked", tone="warn"),
        ],
    )
    run = _replace_step(envelope.run, step.step_id, completed)
    run = _append_artifacts(
        run,
        [
            Artifact("Promotion decision", str(promotion_path.relative_to(project_root)), "report"),
            Artifact("Checkpoint package", str(package_path.relative_to(project_root)), "checkpoint"),
            Artifact("Checkpoint package manifest", str(package_manifest_path.relative_to(project_root)), "report"),
        ],
    )
    run = _replace_headline_metrics(
        run,
        {
            "Promotion": LabMetric("Promotion", "locked", "needs real checkpoint eval", tone="warn"),
        },
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
    if envelope.run.task_type == "Tool calling" and step.step_id == "train":
        return _run_tool_calling_train(project_root, run_dir, envelope)
    if envelope.run.task_type == "Tool calling" and step.step_id == "eval":
        return _run_tool_calling_eval(project_root, run_dir, envelope)
    if envelope.run.task_type == "Tool calling" and step.step_id == "diagnose":
        return _run_tool_calling_diagnose(project_root, run_dir, envelope)
    if envelope.run.task_type == "Tool calling" and step.step_id == "promote":
        return _run_tool_calling_promote(project_root, run_dir, envelope)
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
