from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.niches.text_to_sql.eval import (  # noqa: E402
    evaluate_prediction_records,
    extract_sql,
    spider_examples_to_prompt_records,
)


class TextToSqlEvalTests(unittest.TestCase):
    def _make_db(self, root: Path) -> Path:
        db_dir = root / "database" / "demo"
        db_dir.mkdir(parents=True)
        db_path = db_dir / "demo.sqlite"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("CREATE TABLE orders (order_id INTEGER, customer TEXT, amount REAL)")
            conn.executemany(
                "INSERT INTO orders VALUES (?, ?, ?)",
                [(1, "Alice", 12.5), (2, "Bob", 7.0), (3, "Alice", 5.0)],
            )
            conn.commit()
        finally:
            conn.close()
        return root / "database"

    def test_extract_sql_removes_fences(self) -> None:
        self.assertEqual(extract_sql("```sql\nSELECT 1;\n```"), "SELECT 1")

    def test_evaluate_prediction_records_matches_execution_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database_dir = self._make_db(Path(tmp))
            records = [
                {
                    "example_id": "0",
                    "db_id": "demo",
                    "question": "How many orders are there?",
                    "gold_sql": "SELECT COUNT(*) FROM orders",
                    "predicted_sql": "SELECT COUNT(order_id) FROM orders;",
                },
                {
                    "example_id": "1",
                    "db_id": "demo",
                    "question": "What is Alice's total?",
                    "gold_sql": "SELECT SUM(amount) FROM orders WHERE customer = 'Alice'",
                    "predicted_sql": "SELECT SUM(amount) FROM orders WHERE customer = 'Bob'",
                },
            ]
            results, summary = evaluate_prediction_records(records=records, database_dir=database_dir)
            self.assertTrue(results[0].exact_execution_match)
            self.assertFalse(results[1].exact_execution_match)
            self.assertEqual(summary["correct"], 1)
            self.assertEqual(summary["execution_accuracy"], 0.5)

    def test_spider_examples_to_prompt_records_introspects_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            database_dir = self._make_db(Path(tmp))
            examples = [
                {
                    "db_id": "demo",
                    "question": "How many orders are there?",
                    "query": "SELECT COUNT(*) FROM orders",
                }
            ]
            records = spider_examples_to_prompt_records(examples=examples, database_dir=database_dir)
            self.assertEqual(len(records), 1)
            self.assertIn("CREATE TABLE orders", records[0]["prompt"])
            self.assertEqual(records[0]["gold_sql"], "SELECT COUNT(*) FROM orders")


if __name__ == "__main__":
    unittest.main()
