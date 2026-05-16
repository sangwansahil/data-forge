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
from data_forge.niches.text_to_sql.review import apply_review_decisions  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--accepted", required=True)
    parser.add_argument("--decisions", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--default", choices=["pending", "approve-unreviewed"], default="pending")
    parser.add_argument("--drive-root-id")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    storage = client_for_uri(args.out, drive_root_id=args.drive_root_id, local_root=ROOT)
    summary = apply_review_decisions(
        storage=storage,
        run_id=args.run_id,
        accepted_uri=args.accepted,
        decisions_uri=args.decisions,
        out_uri=args.out,
        default=args.default,
        overwrite=args.force,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
