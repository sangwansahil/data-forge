#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.core.storage import client_for_uri  # noqa: E402
from data_forge.niches.text_to_sql.review import create_signoff  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reviewed", required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--drive-root-id")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    storage = client_for_uri(args.out, drive_root_id=args.drive_root_id, local_root=ROOT)
    signoff = create_signoff(
        storage=storage,
        run_id=args.run_id,
        reviewed_uri=args.reviewed,
        reviewer=args.reviewer,
        out_uri=args.out,
        overwrite=args.force,
    )
    print(json.dumps(signoff, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
