#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.core.storage import (  # noqa: E402
    default_run_base_uri,
    get_storage_client,
    join_uri,
    write_json,
    write_jsonl,
)
from data_forge.niches.text_to_sql.gates import evaluate_text_to_sql_row  # noqa: E402
from data_forge.niches.text_to_sql.review import summarize_rows, utc_now  # noqa: E402


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
        with urllib.request.urlopen(request, timeout=180) as response:
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


def _reason_counts(rejected: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for row in rejected:
        judge = row.get("judge", {})
        if isinstance(judge, dict):
            counter.update(str(reason) for reason in judge.get("reasons", []))
    return dict(counter.most_common())


def _feedback_from_rejections(rejected: list[dict[str, Any]]) -> str:
    reasons = _reason_counts(rejected)
    if not reasons:
        return "Previous batch had no dominant rejection pattern. Increase diversity and difficulty."
    top_reason = next(iter(reasons))
    if "expected_result" in top_reason or "does not match" in top_reason:
        return "Previous batch had result mismatches. Use smaller tables and recompute expected_result exactly."
    if "SQL execution failed" in top_reason:
        return "Previous batch had SQL execution failures. Use conservative SQLite syntax and avoid unsupported functions."
    if "placeholder" in top_reason:
        return "Previous batch had placeholder/meta text. Use realistic row text and concrete business entities."
    return f"Previous batch top rejection reason: {top_reason}. Avoid that failure mode."


def _generate_rows(
    *,
    api_key: str,
    config: dict[str, Any],
    prompt_dir: Path,
    batch_id: str,
    requested_rows: int,
    model: str,
    temperature: float,
    feedback: str,
) -> list[dict[str, Any]]:
    orchestrator_spec = _load_prompt(prompt_dir / "orchestrator_spec.md")
    generator_prompt = _load_prompt(prompt_dir / "deepseek_generator.md")
    payload = {
        "batch_id": batch_id,
        "requested_rows": requested_rows,
        "target_benchmarks": config["target_benchmarks"],
        "skill_mix": config["skill_mix"],
        "domains": config["domains"],
        "acceptance_threshold": config["acceptance_threshold"],
        "row_contract": config["row_contract"],
        "feedback_from_previous_batch": feedback,
    }
    content = _call_deepseek(
        api_key=api_key,
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": orchestrator_spec},
            {"role": "user", "content": generator_prompt + "\n\n" + json.dumps(payload, indent=2)},
        ],
    )
    return _extract_rows(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--target-accepted", type=int, default=5000)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-batches", type=int, default=100)
    parser.add_argument("--storage", choices=["local", "gdrive"], default=os.environ.get("DATA_FORGE_STORAGE", "local"))
    parser.add_argument("--base-uri")
    parser.add_argument("--drive-root-id")
    parser.add_argument("--model")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--min-score", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is required")

    config_path = Path(args.config)
    config = json.loads(config_path.read_text())
    prompt_dir = ROOT / config["prompt_dir"]
    model = args.model or config.get("generator_model", "deepseek-chat")
    temperature = args.temperature if args.temperature is not None else float(config.get("temperature", 0.7))
    min_score = args.min_score if args.min_score is not None else int(config.get("acceptance_threshold", 85))
    base_uri = args.base_uri or default_run_base_uri(args.storage, args.run_id, niche="text-to-sql")
    storage = get_storage_client(storage=args.storage, drive_root_id=args.drive_root_id, local_root=ROOT)

    for folder in ["raw", "accepted", "rejected", "reports", "review", "review/decisions", "reviewed", "datasets", "manifests"]:
        storage.ensure_dir(join_uri(base_uri, folder))

    accepted_total = 0
    batch_reports = []
    feedback = "No previous batch. Prioritize correctness, diversity, and exact expected_result computation."
    for batch_number in range(1, args.max_batches + 1):
        if accepted_total >= args.target_accepted:
            break
        batch_id = f"{args.run_id}_batch_{batch_number:04d}"
        planned_outputs = [
            join_uri(base_uri, "raw", f"{batch_id}.jsonl"),
            join_uri(base_uri, "accepted", f"{batch_id}.jsonl"),
            join_uri(base_uri, "rejected", f"{batch_id}.jsonl"),
            join_uri(base_uri, "reports", f"{batch_id}_validation_report.json"),
        ]
        if not args.force:
            existing = [uri for uri in planned_outputs if storage.exists(uri)]
            if existing:
                raise FileExistsError(
                    f"batch {batch_id} already has output artifacts; pass --force or choose a new --run-id: {existing}"
                )
        rows = _generate_rows(
            api_key=api_key,
            config=config,
            prompt_dir=prompt_dir,
            batch_id=batch_id,
            requested_rows=args.batch_size,
            model=model,
            temperature=temperature,
            feedback=feedback,
        )
        normalized_raw = []
        accepted = []
        rejected = []
        for index, row in enumerate(rows, start=1):
            row = dict(row)
            row["id"] = f"t2sql_{batch_id}_{index:06d}"
            row.setdefault("generation", {})
            row["generation"].update({"generator_model": model, "batch_id": batch_id})
            normalized_raw.append(row)
            result = evaluate_text_to_sql_row(row, min_score=min_score)
            judged = dict(row)
            judged["judge"] = result.to_dict()
            if result.accepted:
                accepted.append(judged)
            else:
                rejected.append(judged)

        raw_result = write_jsonl(storage, join_uri(base_uri, "raw", f"{batch_id}.jsonl"), normalized_raw, overwrite=args.force)
        accepted_result = write_jsonl(
            storage,
            join_uri(base_uri, "accepted", f"{batch_id}.jsonl"),
            accepted,
            overwrite=args.force,
        )
        rejected_result = write_jsonl(
            storage,
            join_uri(base_uri, "rejected", f"{batch_id}.jsonl"),
            rejected,
            overwrite=args.force,
        )
        report = {
            "run_id": args.run_id,
            "batch_id": batch_id,
            "created_at": utc_now(),
            "requested_rows": args.batch_size,
            "raw_count": len(normalized_raw),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "acceptance_rate": len(accepted) / max(1, len(normalized_raw)),
            "top_rejection_reasons": _reason_counts(rejected),
            "accepted_summary": summarize_rows(accepted),
            "artifacts": {
                "raw": raw_result.artifact_id,
                "accepted": accepted_result.artifact_id,
                "rejected": rejected_result.artifact_id,
            },
        }
        write_json(storage, join_uri(base_uri, "reports", f"{batch_id}_validation_report.json"), report, overwrite=args.force)
        accepted_total += len(accepted)
        batch_reports.append(report)
        feedback = _feedback_from_rejections(rejected)
        print(json.dumps({"batch_id": batch_id, "accepted_total": accepted_total, "report": report}, indent=2))

    manifest = {
        "run_id": args.run_id,
        "created_at": utc_now(),
        "base_uri": base_uri,
        "generator_model": model,
        "target_accepted": args.target_accepted,
        "accepted_total": accepted_total,
        "batch_count": len(batch_reports),
        "batch_reports": batch_reports,
    }
    write_json(storage, join_uri(base_uri, "manifests", "generation_manifest.json"), manifest, overwrite=True)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
