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

from data_forge.core.gdrive import GoogleDriveStorageClient  # noqa: E402
from data_forge.core.storage import (  # noqa: E402
    LocalStorageClient,
    default_run_base_uri,
    join_uri,
    read_json_records,
    write_json,
    write_jsonl,
)


class StorageTests(unittest.TestCase):
    def test_local_storage_read_write_list_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorageClient(root=Path(tmp))
            result = storage.write_text("local://runs/a/report.txt", "hello")
            self.assertEqual(result.backend, "local")
            self.assertTrue(storage.exists("local://runs/a/report.txt"))
            self.assertEqual(storage.read_text("local://runs/a/report.txt"), "hello")
            names = [entry.name for entry in storage.list("local://runs/a")]
            self.assertEqual(names, ["report.txt"])

    def test_json_helpers_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = LocalStorageClient(root=Path(tmp))
            write_json(storage, "local://manifest.json", {"ok": True})
            write_jsonl(storage, "local://rows.jsonl", [{"id": "a"}, {"id": "b"}])
            self.assertEqual(json.loads(storage.read_text("local://manifest.json")), {"ok": True})
            self.assertEqual([row["id"] for row in read_json_records(storage, "local://rows.jsonl")], ["a", "b"])

    def test_uri_join_and_default_run_base(self) -> None:
        self.assertEqual(join_uri("gdrive://niches/text-to-sql", "runs", "x"), "gdrive://niches/text-to-sql/runs/x")
        self.assertEqual(join_uri("local://generation", "runs", "x"), "local://generation/runs/x")
        self.assertEqual(default_run_base_uri("gdrive", "abc"), "gdrive://niches/text-to-sql/runs/abc")

    def test_gdrive_path_resolution_does_not_require_api(self) -> None:
        storage = GoogleDriveStorageClient(root_folder_id="root123")
        self.assertEqual(storage._gdrive_path("gdrive://niches/text-to-sql/runs/x"), "niches/text-to-sql/runs/x")


if __name__ == "__main__":
    unittest.main()
