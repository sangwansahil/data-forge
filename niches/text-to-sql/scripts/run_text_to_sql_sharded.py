#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_forge.core.storage import client_for_uri, join_uri  # noqa: E402
from data_forge.niches.text_to_sql.shards import (  # noqa: E402
    ShardSpec,
    SHARD_PROFILES,
    merge_accepted_shards,
    shard_instruction,
)


def _spec_for_index(index: int, profile: str) -> ShardSpec:
    shards = SHARD_PROFILES[profile]
    base = shards[(index - 1) % len(shards)]
    lane = ((index - 1) // len(shards)) + 1
    if lane == 1:
        return base
    return ShardSpec(
        name=f"{base.name}_lane_{lane:02d}",
        domains=base.domains,
        instruction=(
            f"{base.instruction} This is parallel lane {lane} for this domain; use different schema shapes, "
            "entity names, date ranges, metrics, and business questions from other lanes."
        ),
    )


def _shard_run_id(run_id: str, index: int, name: str) -> str:
    safe_name = "".join(char if char.isalnum() or char == "_" else "_" for char in name.lower())
    return f"{run_id}_shard_{index:02d}_{safe_name}"


def _run_command(args: argparse.Namespace, index: int, shard_count: int, log_path: Path) -> list[str]:
    spec = _spec_for_index(index, args.shard_profile)
    shard_run_id = _shard_run_id(args.run_id, index, spec.name)
    base_uri = join_uri(args.base_uri, "shards", shard_run_id)
    command = [
        sys.executable,
        str(ROOT / "niches/text-to-sql/scripts/run_text_to_sql_loop.py"),
        "--config",
        args.config,
        "--run-id",
        shard_run_id,
        "--target-accepted",
        str(args.shard_target_accepted),
        "--batch-size",
        str(args.batch_size),
        "--max-batches",
        str(args.max_batches_per_shard),
        "--max-generation-retries",
        str(args.max_generation_retries),
        "--api-timeout-seconds",
        str(args.api_timeout_seconds),
        "--storage",
        args.storage,
        "--base-uri",
        base_uri,
        "--domains",
        ",".join(spec.domains),
        "--shard-instruction",
        shard_instruction(spec, shard_index=index, shard_count=shard_count),
    ]
    if args.drive_root_id:
        command.extend(["--drive-root-id", args.drive_root_id])
    if args.model:
        command.extend(["--model", args.model])
    if args.force:
        command.append("--force")
    return command


def _poll(processes: dict[str, subprocess.Popen[bytes]], log_paths: dict[str, Path]) -> dict[str, int]:
    exit_codes: dict[str, int] = {}
    while processes:
        finished = []
        for name, process in processes.items():
            exit_code = process.poll()
            if exit_code is None:
                continue
            exit_codes[name] = exit_code
            finished.append(name)
            print(json.dumps({"event": "shard_finished", "shard": name, "exit_code": exit_code, "log": str(log_paths[name])}))
        for name in finished:
            del processes[name]
        if processes:
            print(json.dumps({"event": "shards_running", "count": len(processes), "shards": sorted(processes)}))
            time.sleep(30)
    return exit_codes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="niches/text-to-sql/config.json")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--target-accepted-total", type=int, default=1000)
    parser.add_argument("--shard-count", type=int, default=10)
    parser.add_argument("--shard-profile", choices=sorted(SHARD_PROFILES), default="default")
    parser.add_argument("--parallelism", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--max-batches-per-shard", type=int, default=80)
    parser.add_argument("--max-generation-retries", type=int, default=3)
    parser.add_argument("--api-timeout-seconds", type=int, default=90)
    parser.add_argument("--storage", choices=["local", "gdrive"], default=os.environ.get("DATA_FORGE_STORAGE", "local"))
    parser.add_argument("--base-uri")
    parser.add_argument("--drive-root-id")
    parser.add_argument("--model")
    parser.add_argument("--merge", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.shard_count < 1:
        raise SystemExit("--shard-count must be at least 1")
    if args.parallelism < 1:
        raise SystemExit("--parallelism must be at least 1")
    if not os.environ.get("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY is required")

    args.base_uri = args.base_uri or f"local://generation/niches/text-to-sql/runs/{args.run_id}"
    if args.storage == "gdrive" and not args.base_uri.startswith("gdrive://"):
        args.base_uri = f"gdrive://niches/text-to-sql/runs/{args.run_id}"

    args.shard_target_accepted = max(1, -(-args.target_accepted_total // args.shard_count))
    log_dir = ROOT / "generation/niches/text-to-sql/runs" / args.run_id / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    pending = list(range(1, args.shard_count + 1))
    active: dict[str, subprocess.Popen[bytes]] = {}
    log_paths: dict[str, Path] = {}
    exit_codes: dict[str, int] = {}

    while pending or active:
        while pending and len(active) < args.parallelism:
            index = pending.pop(0)
            spec = _spec_for_index(index, args.shard_profile)
            name = _shard_run_id(args.run_id, index, spec.name)
            log_path = log_dir / f"{name}.log"
            command = _run_command(args, index, args.shard_count, log_path)
            log_handle = log_path.open("w")
            process = subprocess.Popen(command, cwd=ROOT, env=os.environ.copy(), stdout=log_handle, stderr=subprocess.STDOUT)
            log_handle.close()
            active[name] = process
            log_paths[name] = log_path
            print(json.dumps({"event": "shard_started", "shard": name, "domains": spec.domains, "log": str(log_path)}))
        exit_codes.update(_poll(active, log_paths))

    failed = {name: code for name, code in exit_codes.items() if code != 0}
    result = {
        "run_id": args.run_id,
        "base_uri": args.base_uri,
        "shard_count": args.shard_count,
        "shard_profile": args.shard_profile,
        "parallelism": args.parallelism,
        "shard_target_accepted": args.shard_target_accepted,
        "exit_codes": exit_codes,
        "failed": failed,
    }
    if failed:
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    if args.merge:
        storage = client_for_uri(args.base_uri, drive_root_id=args.drive_root_id, local_root=ROOT)
        result["merge_manifest"] = merge_accepted_shards(
            storage=storage,
            run_id=args.run_id,
            shards_uri=join_uri(args.base_uri, "shards"),
            out_uri=join_uri(args.base_uri, "merged"),
            overwrite=args.force,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
