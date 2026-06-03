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


if __name__ == "__main__":
    unittest.main()
