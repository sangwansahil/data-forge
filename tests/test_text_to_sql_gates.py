from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.niches.text_to_sql.gates import evaluate_text_to_sql_row  # noqa: E402
from data_forge.niches.text_to_sql.sqlite_runner import SqlSafetyError, assert_safe_select  # noqa: E402


class TextToSqlGateTests(unittest.TestCase):
    def test_accepts_seed_row(self) -> None:
        row = json.loads((ROOT / "niches/text-to-sql/examples/accepted_row.json").read_text())
        result = evaluate_text_to_sql_row(row)
        self.assertTrue(result.accepted, result.to_dict())
        self.assertGreaterEqual(result.score, 85)

    def test_rejects_placeholder_row(self) -> None:
        row = json.loads((ROOT / "niches/text-to-sql/examples/rejected_row.json").read_text())
        result = evaluate_text_to_sql_row(row)
        self.assertFalse(result.accepted)
        self.assertTrue(any("placeholder" in reason for reason in result.reasons))

    def test_rejects_wrong_expected_result(self) -> None:
        row = json.loads((ROOT / "niches/text-to-sql/examples/accepted_row.json").read_text())
        row["expected_result"] = [{"carrier_name": "UrbanShip", "completed_shipments": 999}]
        result = evaluate_text_to_sql_row(row)
        self.assertFalse(result.accepted)
        self.assertIn("gold_sql result does not match expected_result", result.reasons)

    def test_rejects_mutating_sql(self) -> None:
        with self.assertRaises(SqlSafetyError):
            assert_safe_select("DELETE FROM shipments")


if __name__ == "__main__":
    unittest.main()
