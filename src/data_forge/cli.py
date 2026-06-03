from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_forge import __version__
from data_forge.lab.text_to_sql_demo import build_text_to_sql_demo_card


def _lab_demo(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_card = build_text_to_sql_demo_card(root)
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = root / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(run_card.to_dict(), indent=2, sort_keys=True) + "\n")
    print(out_path)
    return 0


def _lab_inspect(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    run_card = build_text_to_sql_demo_card(root)
    print(f"{run_card.title}")
    print(f"Prompt: {run_card.user_prompt}")
    print(f"Benchmark: {run_card.benchmark}")
    for metric in run_card.headline_metrics:
        suffix = f" ({metric.detail})" if metric.detail else ""
        print(f"- {metric.label}: {metric.value}{suffix}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="data-forge")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.description = "Core data-forge package. Niche-specific commands live under niches/<name>/scripts."
    subparsers = parser.add_subparsers(dest="command")

    lab_parser = subparsers.add_parser("lab", help="Data Forge Lab commands.")
    lab_subparsers = lab_parser.add_subparsers(dest="lab_command")

    demo_parser = lab_subparsers.add_parser("demo", help="Build the static Lab demo run card.")
    demo_parser.add_argument("--root", default=".")
    demo_parser.add_argument("--out", default="apps/lab-ui/demo-run.json")
    demo_parser.set_defaults(func=_lab_demo)

    inspect_parser = lab_subparsers.add_parser("inspect", help="Print the current Lab proof metrics.")
    inspect_parser.add_argument("--root", default=".")
    inspect_parser.set_defaults(func=_lab_inspect)

    args = parser.parse_args()
    if hasattr(args, "func"):
        return args.func(args)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
