from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Optional

StepStatus = Literal["waiting", "needs_approval", "running", "complete", "failed", "blocked"]


@dataclass(frozen=True)
class LabMetric:
    label: str
    value: str
    detail: str = ""
    tone: Literal["neutral", "good", "warn", "bad"] = "neutral"


@dataclass(frozen=True)
class Artifact:
    label: str
    uri: str
    kind: Literal["local", "github", "huggingface", "report", "dataset", "model", "checkpoint"]


@dataclass(frozen=True)
class ApprovalGate:
    gate_id: str
    title: str
    prompt: str
    options: list[str]
    recommended: str
    required: bool = True


@dataclass(frozen=True)
class ModelCandidate:
    model_id: str
    backend: str
    size: str
    license: str
    local_fit: Literal["excellent", "good", "risky", "unknown"]
    rationale: str


@dataclass(frozen=True)
class LabStep:
    step_id: str
    title: str
    agent: str
    status: StepStatus
    summary: str
    details: list[str] = field(default_factory=list)
    metrics: list[LabMetric] = field(default_factory=list)
    approval: Optional[ApprovalGate] = None


@dataclass(frozen=True)
class LabRunCard:
    run_id: str
    title: str
    user_prompt: str
    thesis: str
    mode: Literal["replay", "live", "hybrid"]
    status: Literal["draft", "ready", "running", "complete", "failed"]
    task_type: str
    benchmark: str
    target_metric: str
    model_candidates: list[ModelCandidate]
    steps: list[LabStep]
    headline_metrics: list[LabMetric]
    artifacts: list[Artifact]
    next_loop: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def metric_from_dict(payload: dict[str, Any]) -> LabMetric:
    return LabMetric(**payload)


def artifact_from_dict(payload: dict[str, Any]) -> Artifact:
    return Artifact(**payload)


def approval_from_dict(payload: Optional[dict[str, Any]]) -> Optional[ApprovalGate]:
    return ApprovalGate(**payload) if payload else None


def model_candidate_from_dict(payload: dict[str, Any]) -> ModelCandidate:
    return ModelCandidate(**payload)


def step_from_dict(payload: dict[str, Any]) -> LabStep:
    return LabStep(
        step_id=payload["step_id"],
        title=payload["title"],
        agent=payload["agent"],
        status=payload["status"],
        summary=payload["summary"],
        details=list(payload.get("details", [])),
        metrics=[metric_from_dict(metric) for metric in payload.get("metrics", [])],
        approval=approval_from_dict(payload.get("approval")),
    )


def run_card_from_dict(payload: dict[str, Any]) -> LabRunCard:
    return LabRunCard(
        run_id=payload["run_id"],
        title=payload["title"],
        user_prompt=payload["user_prompt"],
        thesis=payload["thesis"],
        mode=payload["mode"],
        status=payload["status"],
        task_type=payload["task_type"],
        benchmark=payload["benchmark"],
        target_metric=payload["target_metric"],
        model_candidates=[model_candidate_from_dict(model) for model in payload.get("model_candidates", [])],
        steps=[step_from_dict(step) for step in payload.get("steps", [])],
        headline_metrics=[metric_from_dict(metric) for metric in payload.get("headline_metrics", [])],
        artifacts=[artifact_from_dict(artifact) for artifact in payload.get("artifacts", [])],
        next_loop=list(payload.get("next_loop", [])),
    )
