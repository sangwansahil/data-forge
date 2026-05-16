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

from data_forge.core.storage import LocalStorageClient, join_uri, read_json_records, write_json, write_jsonl  # noqa: E402
from data_forge.niches.text_to_sql.gates import evaluate_text_to_sql_row  # noqa: E402
from data_forge.niches.text_to_sql.review import (  # noqa: E402
    apply_review_decisions,
    build_review_packets,
    create_signoff,
    export_sft_dataset,
    row_fingerprint,
)


def _accepted_row(row_id: str) -> dict:
    row = json.loads((ROOT / "niches/text-to-sql/examples/accepted_row.json").read_text())
    row["id"] = row_id
    result = evaluate_text_to_sql_row(row)
    row["judge"] = result.to_dict()
    return row


class TextToSqlReviewTests(unittest.TestCase):
    def test_build_review_packets_chunks_and_contains_export_ui(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorageClient(root=Path(tmp))
            rows = [_accepted_row("row_a"), _accepted_row("row_b")]
            write_jsonl(storage, "local://accepted/rows.jsonl", rows)
            manifest = build_review_packets(
                storage=storage,
                run_id="run_1",
                input_uri="local://accepted",
                out_uri="local://review",
                max_rows=1,
            )
            self.assertEqual(manifest["packet_count"], 2)
            html = storage.read_text("local://review/review_packet_0001.html")
            self.assertIn("Export JSON", html)
            self.assertIn("row_a", html)
            self.assertTrue(storage.exists("local://review/review_manifest.json"))

    def test_apply_review_rejects_bad_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorageClient(root=Path(tmp))
            row = _accepted_row("row_a")
            write_jsonl(storage, "local://accepted/rows.jsonl", [row])
            write_json(
                storage,
                "local://decisions/bad.json",
                {
                    "packet_id": "review_packet_0001",
                    "decisions": [
                        {
                            "row_id": "row_a",
                            "fingerprint": "wrong",
                            "decision": "approve",
                            "reason": "",
                            "note": "",
                        }
                    ],
                },
            )
            with self.assertRaises(ValueError):
                apply_review_decisions(
                    storage=storage,
                    run_id="run_1",
                    accepted_uri="local://accepted",
                    decisions_uri="local://decisions",
                    out_uri="local://reviewed",
                )

    def test_apply_review_splits_approved_rejected_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorageClient(root=Path(tmp))
            rows = [_accepted_row("row_a"), _accepted_row("row_b"), _accepted_row("row_c")]
            write_jsonl(storage, "local://accepted/rows.jsonl", rows)
            write_json(
                storage,
                "local://decisions/decisions.json",
                {
                    "packet_id": "review_packet_0001",
                    "decisions": [
                        {
                            "row_id": "row_a",
                            "fingerprint": row_fingerprint(rows[0]),
                            "decision": "approve",
                            "reason": "",
                            "note": "looks good",
                        },
                        {
                            "row_id": "row_b",
                            "fingerprint": row_fingerprint(rows[1]),
                            "decision": "reject",
                            "reason": "not useful",
                            "note": "",
                        },
                    ],
                },
            )
            summary = apply_review_decisions(
                storage=storage,
                run_id="run_1",
                accepted_uri="local://accepted",
                decisions_uri="local://decisions",
                out_uri="local://reviewed",
            )
            self.assertEqual(summary["approved_count"], 1)
            self.assertEqual(summary["rejected_by_human_count"], 1)
            self.assertEqual(summary["pending_review_count"], 1)
            self.assertEqual(len(read_json_records(storage, "local://reviewed/approved.jsonl")), 1)
            self.assertEqual(len(read_json_records(storage, "local://reviewed/pending_review.jsonl")), 1)

    def test_export_requires_signoff_and_writes_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorageClient(root=Path(tmp))
            rows = [_accepted_row("row_a"), _accepted_row("row_b")]
            write_jsonl(storage, "local://reviewed/approved.jsonl", rows)
            write_jsonl(storage, "local://reviewed/rejected_by_human.jsonl", [])
            write_jsonl(storage, "local://reviewed/pending_review.jsonl", [])

            with self.assertRaises(ValueError):
                export_sft_dataset(
                    storage=storage,
                    input_uri="local://reviewed/approved.jsonl",
                    out_uri="local://datasets/sft_sql_only",
                    signoff_uri=None,
                )

            signoff = create_signoff(
                storage=storage,
                run_id="run_1",
                reviewed_uri="local://reviewed",
                reviewer="sahil",
                out_uri="local://manifests/signoff.json",
            )
            self.assertIn("source_accepted_artifact_ids", signoff)
            self.assertIn("review_decision_artifact_ids", signoff)
            manifest = export_sft_dataset(
                storage=storage,
                input_uri="local://reviewed/approved.jsonl",
                signoff_uri="local://manifests/signoff.json",
                out_uri="local://datasets/sft_sql_only",
            )
            self.assertEqual(sum(manifest["counts"].values()), 2)
            self.assertTrue(storage.exists(join_uri("local://datasets/sft_sql_only", "dataset_manifest.json")))


if __name__ == "__main__":
    unittest.main()
