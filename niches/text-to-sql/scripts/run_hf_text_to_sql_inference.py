#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _load_transformers() -> tuple[object, object]:
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
    except ImportError as exc:
        raise SystemExit(
            "transformers is required for inference. Install optional eval dependencies with: "
            "python3 -m pip install -e '.[eval]'"
        ) from exc
    return AutoModelForCausalLM, AutoTokenizer


def _iter_jsonl(path: Path):
    for line in path.read_text().splitlines():
        if line.strip():
            yield json.loads(line)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True, help="Prompt pack JSONL from build_spider_prompt_pack.py")
    parser.add_argument("--out", required=True)
    parser.add_argument("--max-new-tokens", type=int, default=256)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    AutoModelForCausalLM, AutoTokenizer = _load_transformers()
    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    model = AutoModelForCausalLM.from_pretrained(args.model, device_map="auto", trust_remote_code=True)

    records = list(_iter_jsonl(Path(args.input)))
    if args.limit is not None:
        records = records[: args.limit]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as handle:
        for record in records:
            messages = [
                {"role": "system", "content": "You are an expert Text-to-SQL model. Return correct, executable SQLite SQL only."},
                {"role": "user", "content": record["prompt"]},
            ]
            if hasattr(tokenizer, "apply_chat_template"):
                prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            else:
                prompt = messages[0]["content"] + "\n\n" + messages[1]["content"] + "\n"
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            output = model.generate(
                **inputs,
                max_new_tokens=args.max_new_tokens,
                do_sample=args.temperature > 0,
                temperature=args.temperature if args.temperature > 0 else None,
                pad_token_id=tokenizer.eos_token_id,
            )
            generated = output[0][inputs["input_ids"].shape[-1] :]
            prediction = tokenizer.decode(generated, skip_special_tokens=True).strip()
            payload = dict(record)
            payload["predicted_sql"] = prediction
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
    print(json.dumps({"input": args.input, "out": args.out, "predictions": len(records)}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
