from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

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
    approval: ApprovalGate | None = None


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
