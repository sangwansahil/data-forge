#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.core.storage import client_for_uri  # noqa: E402
from data_forge.niches.text_to_sql.review import build_review_packets  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-rows-per-packet", type=int, default=1000)
    parser.add_argument("--drive-root-id")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    storage = client_for_uri(args.out, drive_root_id=args.drive_root_id, local_root=ROOT)
    manifest = build_review_packets(
        storage=storage,
        run_id=args.run_id,
        input_uri=args.input,
        out_uri=args.out,
        max_rows=args.max_rows_per_packet,
        overwrite=args.force,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
