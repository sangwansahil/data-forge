#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load_mlx():
    try:
        from mlx_lm import generate, load
        from mlx_lm.sample_utils import make_sampler
    except ImportError as exc:
        raise SystemExit(
            "mlx-lm is required for Apple Silicon inference. Install with: "
            "python3 -m pip install -e '.[mlx]'"
        ) from exc
    return load, generate, make_sampler


def _iter_jsonl(path: Path):
    for line in path.read_text().splitlines():
        if line.strip():
            yield json.loads(line)


def _chat_prompt(tokenizer, prompt: str, *, prompt_style: str) -> str:
    system_prompts = {
        "legacy": "You are an expert Text-to-SQL model. Return correct, executable SQLite SQL only.",
        "hardened": "You are an expert Text-to-SQL model. Return exactly one executable SQLite query. Do not think out loud or explain.",
    }
    messages = [
        {
            "role": "system",
            "content": system_prompts[prompt_style],
        },
        {"role": "user", "content": prompt},
    ]
    if hasattr(tokenizer, "apply_chat_template"):
        if prompt_style == "hardened":
            try:
                return tokenizer.apply_chat_template(
                    messages,
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
            except TypeError:
                pass
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    return messages[0]["content"] + "\n\n" + messages[1]["content"] + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="mlx-community/Qwen3-4B-Instruct-2507-4bit")
    parser.add_argument("--adapter-path")
    parser.add_argument("--input", required=True, help="Prompt pack JSONL from build_spider_prompt_pack.py")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--prompt-style", choices=["legacy", "hardened"], default="hardened")
    args = parser.parse_args()

    load, generate, make_sampler = _load_mlx()
    model, tokenizer = load(args.model, adapter_path=args.adapter_path)
    sampler = make_sampler(args.temperature)
    records = list(_iter_jsonl(Path(args.input)))
    if args.limit is not None:
        records = records[: args.limit]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as handle:
        for index, record in enumerate(records, start=1):
            prompt = _chat_prompt(tokenizer, record["prompt"], prompt_style=args.prompt_style)
            prediction = generate(
                model,
                tokenizer,
                prompt=prompt,
                max_tokens=args.max_tokens,
                verbose=False,
                sampler=sampler,
            ).strip()
            payload = dict(record)
            payload["predicted_sql"] = prediction
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
            print(json.dumps({"completed": index, "total": len(records), "example_id": record.get("example_id")}))

    print(json.dumps({"model": args.model, "input": args.input, "out": args.out, "predictions": len(records)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
