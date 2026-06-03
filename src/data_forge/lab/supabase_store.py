from __future__ import annotations

import json
import os
from hashlib import sha256
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from data_forge.lab.executor import run_current_step
from data_forge.lab.planner import plan_lab_run
from data_forge.lab.state import LabRunEnvelope, advance_envelope, refresh_run_status, utc_now


class SupabaseLabRunStore:
    """Supabase-backed store for Lab run snapshots.

    This uses Supabase PostgREST directly so the core package does not need a
    heavyweight client dependency. Server-side code must use a service-role key;
    never expose that key to the static UI.
    """

    def __init__(self, *, url: str, service_role_key: str, artifact_root: Path) -> None:
        self.url = url.rstrip("/")
        self.service_role_key = service_role_key
        self.artifact_root = artifact_root
        self.artifact_root.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls, *, artifact_root: Path) -> "SupabaseLabRunStore":
        url = os.environ.get("SUPABASE_URL", "").strip()
        key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        if not url:
            raise ValueError("SUPABASE_URL is required when DATA_FORGE_LAB_STORE=supabase")
        if not key:
            raise ValueError("SUPABASE_SERVICE_ROLE_KEY is required when DATA_FORGE_LAB_STORE=supabase")
        return cls(url=url, service_role_key=key, artifact_root=artifact_root)

    def run_dir(self, run_id: str) -> Path:
        return self.artifact_root / run_id

    def _request(self, method: str, table_and_query: str, payload: Any = None) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.url}/rest/v1/{table_and_query}",
            data=body,
            method=method,
            headers={
                "apikey": self.service_role_key,
                "Authorization": f"Bearer {self.service_role_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Prefer": "resolution=merge-duplicates,return=representation",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8")
            raise ValueError(f"Supabase request failed: HTTP {exc.code} {detail}") from exc
        return json.loads(text) if text else None

    def _upsert(self, envelope: LabRunEnvelope) -> None:
        run = envelope.run
        payload = envelope.to_dict()
        row = {
            "run_id": run.run_id,
            "title": run.title,
            "user_prompt": run.user_prompt,
            "status": run.status,
            "task_type": run.task_type,
            "benchmark": run.benchmark,
            "current_step_index": envelope.current_step_index,
            "payload": payload,
            "updated_at": envelope.updated_at,
        }
        self._request("POST", "data_forge_lab_runs?on_conflict=run_id", [row])
        for event in envelope.events[-5:]:
            event_json = json.dumps(event, sort_keys=True, separators=(",", ":"))
            event_id = sha256(f"{run.run_id}:{event_json}".encode("utf-8")).hexdigest()
            self._request(
                "POST",
                "data_forge_lab_events?on_conflict=event_id",
                [
                    {
                        "event_id": event_id,
                        "run_id": run.run_id,
                        "event_type": str(event.get("type", "event")),
                        "payload": event,
                    }
                ],
            )
        for artifact in run.artifacts:
            artifact_payload = asdict(artifact)
            artifact_json = json.dumps(artifact_payload, sort_keys=True, separators=(",", ":"))
            artifact_id = sha256(f"{run.run_id}:{artifact_json}".encode("utf-8")).hexdigest()
            self._request(
                "POST",
                "data_forge_lab_artifacts?on_conflict=artifact_id",
                [
                    {
                        "artifact_id": artifact_id,
                        "run_id": run.run_id,
                        "label": artifact.label,
                        "uri": artifact.uri,
                        "kind": artifact.kind,
                        "payload": artifact_payload,
                    }
                ],
            )

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
        self._upsert(envelope)

    def get(self, run_id: str) -> LabRunEnvelope:
        result = self._request(
            "GET",
            "data_forge_lab_runs?select=payload&run_id=eq." + quote(run_id, safe=""),
        )
        if not result:
            raise KeyError(run_id)
        return LabRunEnvelope.from_dict(result[0]["payload"])

    def list(self) -> list[LabRunEnvelope]:
        result = self._request(
            "GET",
            "data_forge_lab_runs?select=payload&order=created_at.asc&limit=50",
        )
        return [LabRunEnvelope.from_dict(row["payload"]) for row in result or []]

    def approve(self, run_id: str, gate_id: str, choice: str = "Approve") -> LabRunEnvelope:
        envelope = self.get(run_id)
        gate_ids = {step.approval.gate_id for step in envelope.run.steps if step.approval}
        if gate_id not in gate_ids:
            raise ValueError(f"unknown approval gate: {gate_id}")
        envelope.approved_gates[gate_id] = choice
        envelope.events.append({"type": "approved", "at": utc_now(), "gate_id": gate_id, "choice": choice})
        advance_envelope(envelope)
        refresh_run_status(envelope)
        self.save(envelope)
        return envelope

    def advance(self, run_id: str) -> LabRunEnvelope:
        envelope = self.get(run_id)
        advance_envelope(envelope)
        refresh_run_status(envelope)
        envelope.events.append({"type": "advanced", "at": utc_now(), "step_index": envelope.current_step_index})
        self.save(envelope)
        return envelope

    def run_next(self, run_id: str, *, project_root: Path) -> LabRunEnvelope:
        envelope = self.get(run_id)
        envelope.run = replace(envelope.run, status="running")
        envelope.events.append({"type": "step_started", "at": utc_now(), "step_index": envelope.current_step_index})
        envelope = run_current_step(
            project_root=project_root,
            run_dir=self.run_dir(run_id) / "artifacts",
            envelope=envelope,
        )
        advance_envelope(envelope)
        refresh_run_status(envelope)
        envelope.events.append({"type": "runner_advanced", "at": utc_now(), "step_index": envelope.current_step_index})
        self.save(envelope)
        return envelope
