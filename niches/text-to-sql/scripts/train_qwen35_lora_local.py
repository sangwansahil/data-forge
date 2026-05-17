#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _load_deps():
    try:
        import torch
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import AutoModelForImageTextToText, AutoProcessor, AutoTokenizer
    except ImportError as exc:
        raise SystemExit(
            "Missing training dependencies. Install with: "
            "python3 -m pip install torch transformers accelerate peft datasets"
        ) from exc
    return torch, AutoProcessor, AutoTokenizer, AutoModelForImageTextToText, LoraConfig, TaskType, get_peft_model


def _read_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows = []
    for line in path.read_text().splitlines():
        if line.strip():
            rows.append(json.loads(line))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _chat_text(tokenizer, messages: list[dict[str, str]], *, add_generation_prompt: bool = False) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=add_generation_prompt)
    return "\n".join(f"{message['role']}: {message['content']}" for message in messages)


def _encode_record(tokenizer, record: dict[str, Any], max_length: int) -> dict[str, list[int]]:
    messages = record["messages"]
    prompt_messages = messages[:-1]
    assistant = str(messages[-1]["content"]).strip()
    prompt_text = _chat_text(tokenizer, prompt_messages, add_generation_prompt=True)
    answer_text = assistant + (tokenizer.eos_token or "")
    prompt_ids = tokenizer(prompt_text, add_special_tokens=False)["input_ids"]
    answer_ids = tokenizer(answer_text, add_special_tokens=False)["input_ids"]
    if len(answer_ids) >= max_length:
        answer_ids = answer_ids[: max_length - 1]
    prompt_budget = max(1, max_length - len(answer_ids))
    prompt_ids = prompt_ids[-prompt_budget:]
    input_ids = list(prompt_ids) + list(answer_ids)
    attention_mask = [1] * len(input_ids)
    labels = [-100] * len(prompt_ids) + list(answer_ids)
    return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


@dataclass
class Collator:
    tokenizer: Any

    def __call__(self, batch: list[dict[str, list[int]]]):
        import torch

        pad_id = self.tokenizer.pad_token_id
        if pad_id is None:
            pad_id = self.tokenizer.eos_token_id
        max_len = max(len(item["input_ids"]) for item in batch)
        input_ids = []
        attention_mask = []
        labels = []
        for item in batch:
            pad = max_len - len(item["input_ids"])
            input_ids.append(item["input_ids"] + [pad_id] * pad)
            attention_mask.append(item["attention_mask"] + [0] * pad)
            labels.append(item["labels"] + [-100] * pad)
        return {
            "input_ids": torch.tensor(input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
            "labels": torch.tensor(labels, dtype=torch.long),
        }


def _discover_lora_targets(model) -> list[str]:
    import torch

    candidates = {
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
        "qkv_proj",
        "out_proj",
        "in_proj",
    }
    found = set()
    for name, module in model.named_modules():
        if isinstance(module, torch.nn.Linear):
            leaf = name.rsplit(".", 1)[-1]
            if leaf in candidates:
                found.add(leaf)
    return sorted(found)


def _move_batch(batch: dict[str, Any], device: str) -> dict[str, Any]:
    return {key: value.to(device) for key, value in batch.items()}


def _eval_loss(model, dataloader, device: str, max_batches: int) -> float | None:
    if dataloader is None or max_batches <= 0:
        return None
    losses = []
    model.eval()
    with __import__("torch").no_grad():
        for index, batch in enumerate(dataloader, start=1):
            if index > max_batches:
                break
            output = model(**_move_batch(batch, device))
            value = float(output.loss.detach().cpu())
            if math.isfinite(value):
                losses.append(value)
    model.train()
    return sum(losses) / len(losses) if losses else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3.5-4B")
    parser.add_argument("--train", required=True)
    parser.add_argument("--validation")
    parser.add_argument("--out", required=True)
    parser.add_argument("--dtype", choices=["auto", "float16", "float32"], default="auto")
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--max-steps", type=int, default=200)
    parser.add_argument("--max-train-samples", type=int)
    parser.add_argument("--max-val-samples", type=int, default=53)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-grad-norm", type=float, default=1.0)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--lora-alpha", type=int, default=32)
    parser.add_argument("--eval-every", type=int, default=50)
    parser.add_argument("--eval-batches", type=int, default=8)
    parser.add_argument("--no-validation", action="store_true")
    args = parser.parse_args()

    torch, AutoProcessor, AutoTokenizer, AutoModelForImageTextToText, LoraConfig, TaskType, get_peft_model = _load_deps()
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    if args.dtype == "float16":
        dtype = torch.float16
    elif args.dtype == "float32":
        dtype = torch.float32
    else:
        dtype = torch.float16 if device == "mps" else torch.float32

    try:
        tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    except Exception:
        processor = AutoProcessor.from_pretrained(args.model, trust_remote_code=True)
        tokenizer = getattr(processor, "tokenizer", processor)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForImageTextToText.from_pretrained(args.model, torch_dtype=dtype, trust_remote_code=True)
    model.config.use_cache = False
    model.to(device)
    if hasattr(model, "gradient_checkpointing_enable"):
        model.gradient_checkpointing_enable()

    targets = _discover_lora_targets(model)
    if not targets:
        raise SystemExit("Could not discover LoRA target modules for this model")
    config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=targets,
    )
    model = get_peft_model(model, config)
    model.print_trainable_parameters()

    train_rows = _read_jsonl(Path(args.train), args.max_train_samples)
    val_rows = [] if args.no_validation or not args.validation else _read_jsonl(Path(args.validation), args.max_val_samples)
    train_data = [_encode_record(tokenizer, row, args.max_length) for row in train_rows]
    val_data = [_encode_record(tokenizer, row, args.max_length) for row in val_rows]
    collator = Collator(tokenizer)
    train_loader = torch.utils.data.DataLoader(train_data, batch_size=args.batch_size, shuffle=True, collate_fn=collator)
    val_loader = (
        torch.utils.data.DataLoader(val_data, batch_size=args.batch_size, shuffle=False, collate_fn=collator)
        if val_data
        else None
    )
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    output_dir = Path(args.out)
    output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = output_dir / "training_metrics.jsonl"
    start = time.time()
    global_step = 0
    optimizer.zero_grad(set_to_none=True)
    last_train_loss = None
    last_val_loss = None

    while global_step < args.max_steps:
        for batch in train_loader:
            output = model(**_move_batch(batch, device))
            loss = output.loss / args.grad_accum
            if not torch.isfinite(loss.detach()):
                raise SystemExit(f"Non-finite training loss at step {global_step + 1}; lower LR or use --dtype float32")
            loss.backward()
            last_train_loss = float((loss.detach() * args.grad_accum).cpu())
            if (global_step + 1) % args.grad_accum == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_grad_norm)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
            global_step += 1
            if global_step % args.eval_every == 0 or global_step == args.max_steps:
                last_val_loss = _eval_loss(model, val_loader, device, args.eval_batches)
                metric = {
                    "step": global_step,
                    "train_loss": round(last_train_loss, 4) if last_train_loss is not None else None,
                    "validation_loss": round(last_val_loss, 4) if last_val_loss is not None else None,
                    "validation_ppl": round(math.exp(last_val_loss), 4) if last_val_loss is not None and last_val_loss < 20 else None,
                    "elapsed_seconds": round(time.time() - start, 2),
                }
                with metrics_path.open("a") as handle:
                    handle.write(json.dumps(metric, sort_keys=True) + "\n")
                print(json.dumps(metric, sort_keys=True), flush=True)
            if global_step >= args.max_steps:
                break

    model.save_pretrained(output_dir / "adapter")
    tokenizer.save_pretrained(output_dir / "adapter")
    summary = {
        "model": args.model,
        "device": device,
        "dtype": str(dtype),
        "train_examples": len(train_rows),
        "validation_examples": len(val_rows),
        "steps": global_step,
        "lora_targets": targets,
        "final_train_loss": round(last_train_loss, 4) if last_train_loss is not None else None,
        "final_validation_loss": round(last_val_loss, 4) if last_val_loss is not None else None,
        "final_validation_ppl": round(math.exp(last_val_loss), 4) if last_val_loss is not None and last_val_loss < 20 else None,
        "elapsed_seconds": round(time.time() - start, 2),
    }
    (output_dir / "training_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
