from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator


def iter_json_records(path: Path) -> Iterator[dict[str, Any]]:
    """Read either a single JSON object/array or newline-delimited JSON."""
    text = path.read_text().strip()
    if not text:
        return

    if path.suffix == ".jsonl":
        for line_no, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if line:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{path}:{line_no}: invalid JSONL line") from exc
        return

    payload = json.loads(text)
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                raise ValueError(f"{path}: JSON array items must be objects")
            yield item
    elif isinstance(payload, dict):
        yield payload
    else:
        raise ValueError(f"{path}: expected JSON object, JSON array, or JSONL")


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
