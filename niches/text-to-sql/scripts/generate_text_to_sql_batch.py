#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]


def _load_prompt(path: Path) -> str:
    return path.read_text().strip()


def _call_deepseek(api_key: str, model: str, messages: list[dict[str, str]], temperature: float) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = json.loads(response.read().decode())
            return body["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"DeepSeek API error {exc.code}: {detail}") from exc


def _extract_rows(content: str) -> list[dict[str, Any]]:
    payload = json.loads(content)
    rows = payload.get("rows", payload)
    if not isinstance(rows, list):
        raise ValueError("generator response must be a JSON object with a rows array")
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("each generated row must be an object")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--rows", type=int, default=20)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model")
    parser.add_argument("--temperature", type=float)
    args = parser.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is required")

    config_path = Path(args.config)
    config = json.loads(config_path.read_text())
    prompt_dir = ROOT / config["prompt_dir"]
    model = args.model or config.get("generator_model", "deepseek-chat")
    temperature = args.temperature if args.temperature is not None else float(config.get("temperature", 0.7))

    orchestrator_spec = _load_prompt(prompt_dir / "orchestrator_spec.md")
    generator_prompt = _load_prompt(prompt_dir / "deepseek_generator.md")

    user_payload = {
        "batch_id": args.batch_id,
        "requested_rows": args.rows,
        "target_benchmarks": config["target_benchmarks"],
        "skill_mix": config["skill_mix"],
        "domains": config["domains"],
        "acceptance_threshold": config["acceptance_threshold"],
        "row_contract": config["row_contract"],
    }

    content = _call_deepseek(
        api_key=api_key,
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": orchestrator_spec},
            {"role": "user", "content": generator_prompt + "\n\n" + json.dumps(user_payload, indent=2)},
        ],
    )
    rows = _extract_rows(content)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as handle:
        for row in rows:
            row.setdefault("generation", {})
            row["generation"].update({"generator_model": model, "batch_id": args.batch_id})
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    print(json.dumps({"wrote": len(rows), "out": str(out_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
