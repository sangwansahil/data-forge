#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-report", required=True)
    parser.add_argument("--finetuned-report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    base = json.loads(Path(args.base_report).read_text())
    finetuned = json.loads(Path(args.finetuned_report).read_text())
    base_acc = float(base.get("execution_accuracy", 0.0))
    finetuned_acc = float(finetuned.get("execution_accuracy", 0.0))
    comparison = {
        "base_report": args.base_report,
        "finetuned_report": args.finetuned_report,
        "base_execution_accuracy": base_acc,
        "finetuned_execution_accuracy": finetuned_acc,
        "absolute_lift": round(finetuned_acc - base_acc, 4),
        "relative_lift": round((finetuned_acc - base_acc) / base_acc, 4) if base_acc else None,
        "base_total": base.get("total"),
        "finetuned_total": finetuned.get("total"),
        "base_correct": base.get("correct"),
        "finetuned_correct": finetuned.get("correct"),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n")
    print(json.dumps(comparison, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
