from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
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

    def test_rejects_unknown_qualified_alias_column(self) -> None:
        row = json.loads((ROOT / "niches/text-to-sql/examples/accepted_row.json").read_text())
        row["gold_sql"] = "SELECT s.carrier_id, s.missing_col FROM shipments AS s;"
        row["expected_result"] = []
        result = evaluate_text_to_sql_row(row)
        self.assertFalse(result.accepted)
        self.assertTrue(any("unknown column" in reason for reason in result.reasons), result.to_dict())

    def test_rejects_wrong_sqlite_function_arity(self) -> None:
        row = json.loads((ROOT / "niches/text-to-sql/examples/accepted_row.json").read_text())
        row["gold_sql"] = "SELECT COALESCE(carrier_id) AS carrier_id FROM shipments;"
        row["expected_result"] = [{"carrier_id": 10}, {"carrier_id": 10}, {"carrier_id": 20}]
        result = evaluate_text_to_sql_row(row)
        self.assertFalse(result.accepted)
        self.assertTrue(any("function arity" in reason for reason in result.reasons), result.to_dict())

    def test_rejects_unstable_output_column_alias(self) -> None:
        row = json.loads((ROOT / "niches/text-to-sql/examples/accepted_row.json").read_text())
        row["gold_sql"] = "SELECT COUNT(*) FROM shipments;"
        row["expected_result"] = [{"COUNT(*)": 3}]
        result = evaluate_text_to_sql_row(row)
        self.assertFalse(result.accepted)
        self.assertTrue(any("stable alias" in reason for reason in result.reasons), result.to_dict())

    def test_allows_cte_alias_references(self) -> None:
        row = json.loads((ROOT / "niches/text-to-sql/examples/accepted_row.json").read_text())
        row["gold_sql"] = (
            "WITH shipment_counts AS ("
            "SELECT carrier_id, COUNT(*) AS completed_shipments "
            "FROM shipments WHERE status = 'completed' GROUP BY carrier_id"
            ") "
            "SELECT sc.carrier_id, sc.completed_shipments "
            "FROM shipment_counts AS sc "
            "WHERE sc.completed_shipments >= 2 "
            "ORDER BY sc.completed_shipments DESC;"
        )
        row["expected_result"] = [{"carrier_id": 2, "completed_shipments": 3}, {"carrier_id": 1, "completed_shipments": 2}]
        result = evaluate_text_to_sql_row(row)
        self.assertTrue(result.accepted, result.to_dict())

    def test_allows_exists_and_comma_joined_cte_aliases(self) -> None:
        row = json.loads((ROOT / "niches/text-to-sql/examples/accepted_row.json").read_text())
        row["gold_sql"] = (
            "WITH completed AS ("
            "SELECT carrier_id, COUNT(*) AS completed_shipments "
            "FROM shipments WHERE status = 'completed' GROUP BY carrier_id"
            "), threshold AS (SELECT 2 AS min_shipments) "
            "SELECT c.carrier_id, c.completed_shipments "
            "FROM completed c, threshold t "
            "WHERE c.completed_shipments >= t.min_shipments "
            "AND EXISTS (SELECT 1 FROM carriers ca WHERE ca.carrier_id = c.carrier_id) "
            "ORDER BY c.completed_shipments DESC;"
        )
        row["expected_result"] = [{"carrier_id": 2, "completed_shipments": 3}, {"carrier_id": 1, "completed_shipments": 2}]
        result = evaluate_text_to_sql_row(row)
        self.assertTrue(result.accepted, result.to_dict())


if __name__ == "__main__":
    unittest.main()
