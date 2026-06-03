from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.lab.planner import plan_lab_run
from data_forge.lab.state import LabRunStore
from data_forge.lab.text_to_sql_demo import build_text_to_sql_demo_card


class LabRunCardTests(unittest.TestCase):
    def test_text_to_sql_demo_card_is_serializable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            card = build_text_to_sql_demo_card(Path(tmp))
        payload = card.to_dict()
        encoded = json.dumps(payload)
        self.assertIn("Text-to-SQL Small Model Lab", encoded)
        self.assertEqual(payload["mode"], "hybrid")
        self.assertEqual(payload["status"], "complete")

    def test_text_to_sql_demo_card_has_closed_loop_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            card = build_text_to_sql_demo_card(Path(tmp))
        step_ids = [step.step_id for step in card.steps]
        self.assertEqual(
            step_ids,
            ["interpret", "benchmark", "model", "forge", "review", "train", "eval", "diagnose", "promote"],
        )
        approval_gates = [step.approval.gate_id for step in card.steps if step.approval]
        self.assertEqual(approval_gates, ["task_interpretation", "model_budget", "dataset_signoff"])

    def test_text_to_sql_demo_card_surfaces_proof_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            card = build_text_to_sql_demo_card(Path(tmp))
        metrics = {metric.label: metric.value for metric in card.headline_metrics}
        self.assertEqual(metrics["Base Qwen3.5-4B"], "40.81%")
        self.assertEqual(metrics["Result-voted system"], "71.47%")
        self.assertEqual(metrics["Improvement"], "+30.66 pts")

    def test_planner_creates_tool_calling_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            card = plan_lab_run("fine tune a small model for tool calling", Path(tmp))
        self.assertEqual(card.task_type, "Tool calling")
        self.assertEqual(card.benchmark, "BFCL-style function calling eval")
        self.assertEqual(card.status, "ready")
        self.assertEqual(card.mode, "live")
        self.assertTrue(card.model_candidates)

    def test_lab_run_store_persists_and_advances_approvals(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = LabRunStore(root / "runs")
            envelope = store.create("fine tune a small model for tool calling", project_root=root)
            self.assertEqual(envelope.current_step_index, 1)
            self.assertEqual(envelope.run.steps[0].approval.gate_id, "task_interpretation")

            envelope = store.approve(envelope.run.run_id, "task_interpretation")
            self.assertEqual(envelope.current_step_index, 2)
            self.assertIn("task_interpretation", envelope.approved_gates)

            envelope = store.approve(envelope.run.run_id, "benchmark_plan")
            self.assertEqual(envelope.current_step_index, 3)

            envelope = store.approve(envelope.run.run_id, "model_budget")
            self.assertEqual(envelope.current_step_index, 4)

            reloaded = store.get(envelope.run.run_id)
            self.assertEqual(reloaded.current_step_index, 4)
            self.assertIn("model_budget", reloaded.approved_gates)

    def test_lab_run_store_runs_tool_calling_baseline_and_forge_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture_dir = root / "niches/tool-calling/examples"
            fixture_dir.mkdir(parents=True)
            fixture = ROOT / "niches/tool-calling/examples/eval_cases.jsonl"
            (fixture_dir / "eval_cases.jsonl").write_text(fixture.read_text())

            store = LabRunStore(root / "runs")
            envelope = store.create("fine tune a small model for tool calling", project_root=root)
            run_id = envelope.run.run_id
            for gate_id in ["task_interpretation", "benchmark_plan", "model_budget"]:
                envelope = store.approve(run_id, gate_id)

            self.assertEqual(envelope.run.steps[envelope.current_step_index - 1].step_id, "baseline")
            envelope = store.run_next(run_id, project_root=root)
            self.assertEqual(envelope.run.steps[3].status, "complete")
            self.assertEqual(envelope.current_step_index, 5)
            self.assertTrue((root / "runs" / run_id / "artifacts/tool_calling/baseline_report.json").exists())

            envelope = store.run_next(run_id, project_root=root)
            self.assertEqual(envelope.run.steps[4].status, "complete")
            self.assertEqual(envelope.current_step_index, 6)
            self.assertTrue((root / "runs" / run_id / "artifacts/tool_calling/seed_rows.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
