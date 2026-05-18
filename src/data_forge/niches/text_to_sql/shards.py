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

SPIDER_GAP_SHARDS = [
    ShardSpec(
        name="cars_makers_specs",
        domains=["cars_makers_specs"],
        instruction=(
            "Focus on car makers, models, specs, horsepower, weight, year, country, and maker/model bridge tables. "
            "Create multi-hop joins, top-k superlatives, average-comparison subqueries, and exact answer-shape traps."
        ),
    ),
    ShardSpec(
        name="geography_languages",
        domains=["geography_languages"],
        instruction=(
            "Focus on countries, cities, regions, continents, government forms, populations, and country-language percentages. "
            "Create schema-linking traps with Code versus Name, exact literal matching, joins, grouping, and top language questions."
        ),
    ),
    ShardSpec(
        name="sports_players_matches",
        domains=["sports_players_matches"],
        instruction=(
            "Focus on players, matches, rankings, tournaments, winners, losers, ages, and country codes. "
            "Create INTERSECT/EXCEPT cases, rank semantics where lower rank is better, and exact output-column questions."
        ),
    ),
    ShardSpec(
        name="education_transcripts",
        domains=["education_transcripts"],
        instruction=(
            "Focus on departments, degree programs, courses, sections, students, transcripts, semesters, and instructors. "
            "Create GROUP BY/HAVING, most/least departments, substring LIKE traps, and schema-linking ambiguity."
        ),
    ),
    ShardSpec(
        name="pets_treatments",
        domains=["pets_treatments"],
        instruction=(
            "Focus on dogs, owners, professionals, treatments, costs, breeds, and visits. "
            "Create anti-joins, NOT IN, UNION/EXCEPT, treatment-cost thresholds, and include/exclude entity wording traps."
        ),
    ),
    ShardSpec(
        name="concerts_stadiums",
        domains=["concerts_stadiums"],
        instruction=(
            "Focus on singers, songs, concerts, stadiums, capacities, attendance averages, and participation bridge tables. "
            "Create top-k, aggregation versus column-name traps, multi-table joins, and exact answer-shape questions."
        ),
    ),
    ShardSpec(
        name="real_estate_assets",
        domains=["real_estate_assets"],
        instruction=(
            "Focus on properties, owners, addresses, rooms, features, prices, leases, and inspections. "
            "Create long SQL, nested subqueries, null handling, and exact requested-column outputs."
        ),
    ),
    ShardSpec(
        name="flights_routes",
        domains=["flights_routes"],
        instruction=(
            "Focus on airports, airlines, routes, flights, aircraft, delays, and city/country codes. "
            "Create multi-hop joins, set operations, date filters, and origin/destination schema-linking traps."
        ),
    ),
    ShardSpec(
        name="documents_templates",
        domains=["documents_templates"],
        instruction=(
            "Focus on documents, templates, paragraphs, users, roles, statuses, and revisions. "
            "Create nested queries, GROUP BY/HAVING, optional relationships, and exact output shape traps."
        ),
    ),
    ShardSpec(
        name="network_assets",
        domains=["network_assets"],
        instruction=(
            "Focus on devices, ports, links, VLANs, incidents, locations, owners, and maintenance records. "
            "Create 3-4 table joins, anti-joins, ambiguous id/name columns, and long SQL with conservative SQLite syntax."
        ),
    ),
]

SHARD_PROFILES = {
    "default": DEFAULT_SHARDS,
    "spider_gap": SPIDER_GAP_SHARDS,
}


def shard_instruction(spec: ShardSpec, *, shard_index: int, shard_count: int) -> str:
    return (
        f"This is shard {shard_index} of {shard_count}. Generate only the assigned domain(s): "
        f"{', '.join(spec.domains)}. {spec.instruction} "
        "Prioritize exact expected_result computation and exact answer shape. Include mostly hard and expert rows unless the "
        "run config says otherwise. Use underrepresented skills when natural: set operations, schema-linking traps, "
        "null handling, anti-joins, conditional aggregation, nested queries, multi-hop joins, and GROUP BY/HAVING."
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
