from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.core.storage import LocalStorageClient, write_jsonl  # noqa: E402
from data_forge.niches.text_to_sql.shards import merge_accepted_shards  # noqa: E402


class TextToSqlShardTests(unittest.TestCase):
    def test_merge_dedupes_accepted_rows_by_fingerprint(self) -> None:
        seed = json.loads((ROOT / "niches/text-to-sql/examples/accepted_row.json").read_text())
        duplicate = dict(seed)
        duplicate["id"] = "duplicate_id"
        other = dict(seed)
        other["id"] = "other_id"
        other["instruction"] = "Which carriers completed exactly one delivered shipment?"
        other["gold_sql"] = (
            "SELECT carrier_name, completed_shipments FROM ("
            "SELECT c.carrier_name, COUNT(*) AS completed_shipments "
            "FROM carriers c JOIN shipments s ON c.carrier_id = s.carrier_id "
            "WHERE s.status = 'delivered' GROUP BY c.carrier_name"
            ") WHERE completed_shipments = 1;"
        )
        other["expected_result"] = [{"carrier_name": "RiverLine", "completed_shipments": 1}]

        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorageClient(root=Path(tmp))
            write_jsonl(storage, "local://runs/demo/shards/shard_01/accepted/a.jsonl", [seed], overwrite=True)
            write_jsonl(storage, "local://runs/demo/shards/shard_01/rejected/r.jsonl", [], overwrite=True)
            write_jsonl(storage, "local://runs/demo/shards/shard_02/accepted/a.jsonl", [duplicate, other], overwrite=True)
            write_jsonl(storage, "local://runs/demo/shards/shard_02/rejected/r.jsonl", [], overwrite=True)

            manifest = merge_accepted_shards(
                storage=storage,
                run_id="demo",
                shards_uri="local://runs/demo/shards",
                out_uri="local://runs/demo/merged",
                overwrite=True,
            )

            self.assertEqual(manifest["accepted_count"], 2)
            self.assertEqual(manifest["duplicate_count"], 1)
            merged = (Path(tmp) / "runs/demo/merged/accepted.jsonl").read_text().splitlines()
            duplicates = (Path(tmp) / "runs/demo/merged/duplicates.jsonl").read_text().splitlines()
            self.assertEqual(len(merged), 2)
            self.assertEqual(len(duplicates), 1)


if __name__ == "__main__":
    unittest.main()
