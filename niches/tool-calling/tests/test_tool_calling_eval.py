from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.niches.tool_calling.eval import evaluate_tool_call_records  # noqa: E402


class ToolCallingEvalTests(unittest.TestCase):
    def test_exact_tool_call_match(self) -> None:
        _, summary = evaluate_tool_call_records(
            [
                {
                    "example_id": "a",
                    "expected_calls": [{"name": "search", "arguments": {"query": "Acme"}}],
                    "predicted_calls": [{"name": "search", "arguments": {"query": "Acme"}}],
                }
            ]
        )
        self.assertEqual(summary["exact_accuracy"], 1.0)
        self.assertEqual(summary["tool_selection_accuracy"], 1.0)

    def test_no_tool_relevance_match(self) -> None:
        _, summary = evaluate_tool_call_records([{"example_id": "a", "expected_calls": [], "predicted_calls": []}])
        self.assertEqual(summary["exact_accuracy"], 1.0)

    def test_argument_mismatch_fails_exact_match(self) -> None:
        _, summary = evaluate_tool_call_records(
            [
                {
                    "example_id": "a",
                    "expected_calls": [{"name": "search", "arguments": {"query": "Acme"}}],
                    "predicted_calls": [{"name": "search", "arguments": {"query": "Globex"}}],
                }
            ]
        )
        self.assertEqual(summary["tool_selection_accuracy"], 1.0)
        self.assertEqual(summary["argument_accuracy"], 0.0)
        self.assertEqual(summary["exact_accuracy"], 0.0)

    def test_invalid_json_prediction_is_reported(self) -> None:
        _, summary = evaluate_tool_call_records(
            [{"example_id": "a", "expected_calls": [], "predicted_calls": "{not json"}]
        )
        self.assertEqual(summary["valid_prediction_rate"], 0.0)
        self.assertTrue(summary["top_errors"])


if __name__ == "__main__":
    unittest.main()
