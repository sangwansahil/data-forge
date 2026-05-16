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
from data_forge.niches.text_to_sql.review import export_sft_dataset  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--signoff")
    parser.add_argument("--out", required=True)
    parser.add_argument("--train-ratio", type=float, default=0.9)
    parser.add_argument("--val-ratio", type=float, default=0.05)
    parser.add_argument("--test-ratio", type=float, default=0.05)
    parser.add_argument("--unsafe-skip-review-signoff", action="store_true")
    parser.add_argument("--drive-root-id")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    storage = client_for_uri(args.out, drive_root_id=args.drive_root_id, local_root=ROOT)
    manifest = export_sft_dataset(
        storage=storage,
        input_uri=args.input,
        out_uri=args.out,
        signoff_uri=args.signoff,
        unsafe_skip_review_signoff=args.unsafe_skip_review_signoff,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
        test_ratio=args.test_ratio,
        overwrite=args.force,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
