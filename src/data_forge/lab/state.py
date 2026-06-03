from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from data_forge.lab.planner import plan_lab_run
from data_forge.lab.run_card import LabRunCard, run_card_from_dict


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class LabRunEnvelope:
    run: LabRunCard
    current_step_index: int
    approved_gates: dict[str, str] = field(default_factory=dict)
    events: list[dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run": self.run.to_dict(),
            "state": {
                "current_step_index": self.current_step_index,
                "approved_gates": self.approved_gates,
                "events": self.events,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "LabRunEnvelope":
        state = payload.get("state", {})
        return cls(
            run=run_card_from_dict(payload["run"]),
            current_step_index=int(state.get("current_step_index", 1)),
            approved_gates=dict(state.get("approved_gates", {})),
            events=list(state.get("events", [])),
            created_at=str(state.get("created_at", utc_now())),
            updated_at=str(state.get("updated_at", utc_now())),
        )


class LabRunStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def run_dir(self, run_id: str) -> Path:
        return self.root / run_id

    def run_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def create(self, prompt: str, *, project_root: Path) -> LabRunEnvelope:
        run = plan_lab_run(prompt, project_root)
        envelope = LabRunEnvelope(
            run=run,
            current_step_index=1 if run.steps else 0,
            events=[{"type": "created", "at": utc_now(), "prompt": prompt}],
        )
        self.save(envelope)
        return envelope

    def save(self, envelope: LabRunEnvelope) -> None:
        envelope.updated_at = utc_now()
        path = self.run_path(envelope.run.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(envelope.to_dict(), indent=2, sort_keys=True) + "\n")

    def get(self, run_id: str) -> LabRunEnvelope:
        path = self.run_path(run_id)
        if not path.exists():
            raise KeyError(run_id)
        return LabRunEnvelope.from_dict(json.loads(path.read_text()))

    def list(self) -> list[LabRunEnvelope]:
        envelopes = []
        for path in sorted(self.root.glob("*/run.json")):
            envelopes.append(LabRunEnvelope.from_dict(json.loads(path.read_text())))
        return envelopes

    def approve(self, run_id: str, gate_id: str, choice: str = "Approve") -> LabRunEnvelope:
        envelope = self.get(run_id)
        gate_ids = {step.approval.gate_id for step in envelope.run.steps if step.approval}
        if gate_id not in gate_ids:
            raise ValueError(f"unknown approval gate: {gate_id}")
        envelope.approved_gates[gate_id] = choice
        envelope.events.append({"type": "approved", "at": utc_now(), "gate_id": gate_id, "choice": choice})
        self._advance(envelope)
        self.save(envelope)
        return envelope

    def advance(self, run_id: str) -> LabRunEnvelope:
        envelope = self.get(run_id)
        self._advance(envelope)
        envelope.events.append({"type": "advanced", "at": utc_now(), "step_index": envelope.current_step_index})
        self.save(envelope)
        return envelope

    def _advance(self, envelope: LabRunEnvelope) -> None:
        steps = envelope.run.steps
        if not steps:
            envelope.current_step_index = 0
            return
        if envelope.current_step_index < 1:
            envelope.current_step_index = 1
        while envelope.current_step_index <= len(steps):
            current = steps[envelope.current_step_index - 1]
            if current.approval and current.approval.gate_id not in envelope.approved_gates:
                break
            if envelope.current_step_index == len(steps):
                break
            envelope.current_step_index += 1
