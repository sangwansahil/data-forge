from __future__ import annotations

import argparse
from data_forge import __version__


def main() -> int:
    parser = argparse.ArgumentParser(prog="data-forge")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.description = "Core data-forge package. Niche-specific commands live under niches/<name>/scripts."
    args = parser.parse_args()
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
