from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from data_forge.core.storage import StorageClient, join_uri, read_json_records, write_json, write_jsonl
from data_forge.niches.text_to_sql.review import row_fingerprint, summarize_rows, utc_now


@dataclass(frozen=True)
class ShardSpec:
    name: str
    domains: list[str]
    instruction: str


DEFAULT_SHARDS = [
    ShardSpec(
        name="support_ops",
        domains=["support_operations"],
        instruction="Focus on support queues, tickets, escalations, SLA breaches, customer segments, agent performance, and unresolved issue analysis.",
    ),
    ShardSpec(
        name="media_analytics",
        domains=["media_analytics"],
        instruction="Focus on streams, creators, campaigns, cohorts, retention, catalog performance, attribution, and date-windowed analytics.",
    ),
    ShardSpec(
        name="marketplace",
        domains=["marketplace"],
        instruction="Focus on buyers, sellers, listings, orders, refunds, disputes, commissions, and marketplace health metrics.",
    ),
    ShardSpec(
        name="finance_ops",
        domains=["finance_ops"],
        instruction="Focus on invoices, payments, budgets, expense reports, collections, revenue recognition, and reconciliation.",
    ),
    ShardSpec(
        name="ecommerce",
        domains=["ecommerce"],
        instruction="Focus on orders, products, carts, discounts, late shipments, cohorts, category analytics, and refunds.",
    ),
    ShardSpec(
        name="healthcare_admin",
        domains=["healthcare_admin"],
        instruction="Focus on appointments, providers, patients, authorizations, referrals, billing queues, and operational healthcare admin analytics.",
    ),
    ShardSpec(
        name="logistics",
        domains=["logistics"],
        instruction="Focus on shipments, routes, carriers, warehouses, delivery exceptions, lead times, capacity, and on-time performance.",
    ),
    ShardSpec(
        name="warehouse_inventory",
        domains=["warehouse_inventory"],
        instruction="Focus on stock movements, reorder points, cycle counts, bins, suppliers, demand, shrinkage, and fulfillment constraints.",
    ),
    ShardSpec(
        name="education_admin",
        domains=["education_admin"],
        instruction="Focus on enrollments, attendance, courses, instructors, grades, prerequisites, advising, and student support operations.",
    ),
    ShardSpec(
        name="saas_metrics",
        domains=["saas_metrics"],
        instruction="Focus on subscriptions, plans, renewals, churn, expansion, seats, usage, activation, and account health.",
    ),
]


def shard_instruction(spec: ShardSpec, *, shard_index: int, shard_count: int) -> str:
    return (
        f"This is shard {shard_index} of {shard_count}. Generate only the assigned domain(s): "
        f"{', '.join(spec.domains)}. {spec.instruction} "
        "Prioritize exact expected_result computation. Include a balanced mix of easy, medium, hard, and expert rows. "
        "Use underrepresented skills when natural: set operations, schema-linking traps, null handling, anti-joins, and conditional aggregation."
    )


def merge_accepted_shards(
    *,
    storage: StorageClient,
    run_id: str,
    shards_uri: str,
    out_uri: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    merged: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    shard_summaries = []

    for shard_entry in storage.list(shards_uri):
        if not shard_entry.is_dir:
            continue
        accepted_uri = join_uri(shard_entry.uri, "accepted")
        rejected_uri = join_uri(shard_entry.uri, "rejected")
        accepted_rows = read_json_records(storage, accepted_uri)
        rejected_rows = read_json_records(storage, rejected_uri) if storage.exists(rejected_uri) else []
        kept = 0
        duplicate_count = 0
        for row in accepted_rows:
            fingerprint = row_fingerprint(row)
            if fingerprint in seen:
                duplicate = dict(row)
                duplicate["duplicate_of"] = seen[fingerprint]
                duplicates.append(duplicate)
                duplicate_count += 1
                continue
            seen[fingerprint] = str(row.get("id", ""))
            merged.append(row)
            kept += 1
        shard_summaries.append(
            {
                "shard": shard_entry.name,
                "accepted_input": len(accepted_rows),
                "accepted_kept": kept,
                "duplicates": duplicate_count,
                "rejected": len(rejected_rows),
                "summary": summarize_rows(accepted_rows),
            }
        )

    accepted_result = write_jsonl(storage, join_uri(out_uri, "accepted.jsonl"), merged, overwrite=overwrite)
    duplicates_result = write_jsonl(storage, join_uri(out_uri, "duplicates.jsonl"), duplicates, overwrite=overwrite)
    manifest = {
        "run_id": run_id,
        "created_at": utc_now(),
        "shards_uri": shards_uri,
        "out_uri": out_uri,
        "accepted_count": len(merged),
        "duplicate_count": len(duplicates),
        "summary": summarize_rows(merged),
        "shards": shard_summaries,
        "artifacts": {
            "accepted": accepted_result.artifact_id,
            "duplicates": duplicates_result.artifact_id,
        },
    }
    write_json(storage, join_uri(out_uri, "merge_manifest.json"), manifest, overwrite=overwrite)
    return manifest
