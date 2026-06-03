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

from data_forge.lab.text_to_sql_demo import build_text_to_sql_demo_card  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static Data Forge Lab demo run manifest.")
    parser.add_argument("--out", default="apps/lab-ui/demo-run.json")
    parser.add_argument("--js-out", default="apps/lab-ui/demo-run.js")
    args = parser.parse_args()

    run_card = build_text_to_sql_demo_card(ROOT)
    payload = json.dumps(run_card.to_dict(), indent=2, sort_keys=True)
    out_path = ROOT / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(payload + "\n")
    js_out_path = ROOT / args.js_out
    js_out_path.parent.mkdir(parents=True, exist_ok=True)
    js_out_path.write_text("window.DATA_FORGE_DEMO_RUN = " + payload + ";\n")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
