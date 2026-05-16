from __future__ import annotations

import html
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable

from data_forge.core.storage import (
    StorageClient,
    join_uri,
    read_json_records,
    write_json,
    write_jsonl,
)
from data_forge.niches.text_to_sql.export import row_to_sft_record
from data_forge.niches.text_to_sql.gates import stable_row_fingerprint

GATE_VERSION = "text-to-sql-gates-v1"
VALID_DECISIONS = {"approve", "reject", "flag"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def row_fingerprint(row: dict[str, Any]) -> str:
    judge = row.get("judge")
    if isinstance(judge, dict):
        metadata = judge.get("metadata")
        if isinstance(metadata, dict) and metadata.get("fingerprint"):
            return str(metadata["fingerprint"])
    return stable_row_fingerprint(row)


def load_rows(storage: StorageClient, uri: str) -> list[dict[str, Any]]:
    return read_json_records(storage, uri)


def _skills(row: dict[str, Any]) -> list[str]:
    skills = row.get("skills", [])
    if isinstance(skills, list):
        return [str(skill) for skill in skills]
    return []


def summarize_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(rows)
    domains = Counter(str(row.get("domain", "unknown")) for row in rows)
    difficulties = Counter(str(row.get("difficulty", "unknown")) for row in rows)
    skill_counts: Counter[str] = Counter()
    scores = []
    for row in rows:
        skill_counts.update(_skills(row))
        judge = row.get("judge")
        if isinstance(judge, dict) and isinstance(judge.get("score"), int):
            scores.append(judge["score"])
    return {
        "row_count": len(rows),
        "domains": dict(sorted(domains.items())),
        "difficulties": dict(sorted(difficulties.items())),
        "skills": dict(sorted(skill_counts.items())),
        "score_min": min(scores) if scores else None,
        "score_max": max(scores) if scores else None,
        "score_avg": round(sum(scores) / len(scores), 2) if scores else None,
    }


def _safe_json_script(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True).replace("</", "<\\/")


def _schema_summary(row: dict[str, Any]) -> str:
    schema = row.get("schema", {})
    tables = schema.get("tables", []) if isinstance(schema, dict) else []
    parts = []
    for table in tables:
        columns = table.get("columns", []) if isinstance(table, dict) else []
        col_names = [str(column.get("name")) for column in columns if isinstance(column, dict)]
        parts.append(f"{table.get('name', 'unknown')}({', '.join(col_names)})")
    return "; ".join(parts)


def _prepare_viewer_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for row in rows:
        copy = dict(row)
        copy["review_fingerprint"] = row_fingerprint(row)
        copy["schema_summary"] = _schema_summary(row)
        prepared.append(copy)
    return prepared


def build_review_html(packet_id: str, run_id: str, rows: list[dict[str, Any]]) -> str:
    payload = {
        "packet_id": packet_id,
        "run_id": run_id,
        "generated_at": utc_now(),
        "rows": _prepare_viewer_rows(rows),
    }
    data = _safe_json_script(payload)
    title = html.escape(f"data-forge review {packet_id}")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #101214;
      --panel: #171b20;
      --muted: #9aa4b2;
      --text: #f4f7fb;
      --line: #2a313a;
      --accent: #6bd1ff;
      --good: #44d18c;
      --bad: #ff7373;
      --warn: #ffc857;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    header {{
      position: sticky;
      top: 0;
      z-index: 2;
      border-bottom: 1px solid var(--line);
      background: rgba(16, 18, 20, 0.96);
      padding: 14px 18px;
    }}
    h1 {{ margin: 0 0 10px; font-size: 20px; }}
    .controls {{
      display: grid;
      grid-template-columns: minmax(220px, 2fr) repeat(5, minmax(120px, 1fr)) auto auto;
      gap: 8px;
      align-items: center;
    }}
    input, select, textarea, button {{
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--text);
      border-radius: 6px;
      padding: 8px 10px;
      font: inherit;
    }}
    button {{ cursor: pointer; }}
    button.approve {{ border-color: rgba(68, 209, 140, .7); }}
    button.reject {{ border-color: rgba(255, 115, 115, .7); }}
    button.flag {{ border-color: rgba(255, 200, 87, .7); }}
    main {{
      display: grid;
      grid-template-columns: 420px 1fr;
      min-height: calc(100vh - 92px);
    }}
    .list {{ border-right: 1px solid var(--line); overflow: auto; }}
    .row-card {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      cursor: pointer;
    }}
    .row-card.active {{ background: #202832; }}
    .row-card strong {{ display: block; margin-bottom: 4px; }}
    .meta {{ color: var(--muted); font-size: 12px; line-height: 1.5; }}
    .badge {{
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 1px 7px;
      margin: 2px 3px 0 0;
      font-size: 12px;
      color: var(--muted);
    }}
    .detail {{ padding: 18px; overflow: auto; }}
    .section {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 14px;
      margin-bottom: 12px;
    }}
    .section h2 {{ font-size: 14px; margin: 0 0 10px; color: var(--accent); }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      margin: 0;
      font: 13px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 6px; text-align: left; vertical-align: top; }}
    .actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }}
    .status-approve {{ color: var(--good); }}
    .status-reject {{ color: var(--bad); }}
    .status-flag {{ color: var(--warn); }}
    .empty {{ color: var(--muted); padding: 24px; }}
    @media (max-width: 900px) {{
      .controls {{ grid-template-columns: 1fr 1fr; }}
      main {{ grid-template-columns: 1fr; }}
      .list {{ border-right: 0; max-height: 45vh; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>data-forge Text-to-SQL Review: {html.escape(packet_id)}</h1>
    <div class="controls">
      <input id="search" placeholder="Search rows, SQL, schema, skills">
      <select id="domain"></select>
      <select id="difficulty"></select>
      <select id="skill"></select>
      <select id="status"></select>
      <input id="reviewer" placeholder="Reviewer name">
      <button id="bulkApprove" class="approve">Approve visible</button>
      <button id="exportDecisions">Export JSON</button>
    </div>
  </header>
  <main>
    <div id="list" class="list"></div>
    <div id="detail" class="detail"><div class="empty">Select a row to inspect it.</div></div>
  </main>
  <script id="rows-data" type="application/json">{data}</script>
  <script>
    const packet = JSON.parse(document.getElementById('rows-data').textContent);
    const rows = packet.rows;
    const decisions = JSON.parse(localStorage.getItem(packet.packet_id + ':decisions') || '{{}}');
    let selectedId = rows[0]?.id || null;

    const els = {{
      search: document.getElementById('search'),
      domain: document.getElementById('domain'),
      difficulty: document.getElementById('difficulty'),
      skill: document.getElementById('skill'),
      status: document.getElementById('status'),
      reviewer: document.getElementById('reviewer'),
      list: document.getElementById('list'),
      detail: document.getElementById('detail'),
      bulkApprove: document.getElementById('bulkApprove'),
      exportDecisions: document.getElementById('exportDecisions')
    }};

    function uniq(values) {{
      return Array.from(new Set(values.filter(Boolean))).sort();
    }}
    function fillSelect(el, label, values) {{
      el.innerHTML = `<option value="">${{label}}</option>` + values.map(v => `<option value="${{escapeHtml(v)}}">${{escapeHtml(v)}}</option>`).join('');
    }}
    function escapeHtml(value) {{
      return String(value ?? '').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    }}
    function rowText(row) {{
      return JSON.stringify([row.id, row.domain, row.difficulty, row.skills, row.instruction, row.schema_summary, row.gold_sql]).toLowerCase();
    }}
    function decisionFor(row) {{
      return decisions[row.id]?.decision || 'pending';
    }}
    function filteredRows() {{
      const query = els.search.value.trim().toLowerCase();
      return rows.filter(row => {{
        if (query && !rowText(row).includes(query)) return false;
        if (els.domain.value && row.domain !== els.domain.value) return false;
        if (els.difficulty.value && row.difficulty !== els.difficulty.value) return false;
        if (els.skill.value && !(row.skills || []).includes(els.skill.value)) return false;
        if (els.status.value && decisionFor(row) !== els.status.value) return false;
        return true;
      }});
    }}
    function renderList() {{
      const visible = filteredRows();
      if (!visible.some(row => row.id === selectedId)) selectedId = visible[0]?.id || null;
      els.list.innerHTML = visible.map(row => {{
        const judge = row.judge || {{}};
        const status = decisionFor(row);
        return `<div class="row-card ${{row.id === selectedId ? 'active' : ''}}" data-id="${{escapeHtml(row.id)}}">
          <strong>${{escapeHtml(row.id)}} <span class="status-${{escapeHtml(status)}}">${{escapeHtml(status)}}</span></strong>
          <div class="meta">${{escapeHtml(row.domain)}} / ${{escapeHtml(row.difficulty)}} / score ${{escapeHtml(judge.score ?? 'n/a')}}</div>
          <div>${{(row.skills || []).map(skill => `<span class="badge">${{escapeHtml(skill)}}</span>`).join('')}}</div>
          <div class="meta">${{escapeHtml(row.instruction).slice(0, 170)}}</div>
        </div>`;
      }}).join('') || '<div class="empty">No rows match the filters.</div>';
      els.list.querySelectorAll('.row-card').forEach(card => {{
        card.addEventListener('click', () => {{
          selectedId = card.dataset.id;
          render();
        }});
      }});
    }}
    function renderTable(rows) {{
      if (!Array.isArray(rows) || rows.length === 0) return '<div class="meta">No rows.</div>';
      const keys = Array.from(new Set(rows.flatMap(row => Object.keys(row))));
      return `<table><thead><tr>${{keys.map(key => `<th>${{escapeHtml(key)}}</th>`).join('')}}</tr></thead><tbody>` +
        rows.map(row => `<tr>${{keys.map(key => `<td>${{escapeHtml(row[key])}}</td>`).join('')}}</tr>`).join('') +
        '</tbody></table>';
    }}
    function renderDetail() {{
      const row = rows.find(item => item.id === selectedId);
      if (!row) {{
        els.detail.innerHTML = '<div class="empty">Select a row to inspect it.</div>';
        return;
      }}
      const judge = row.judge || {{}};
      const current = decisions[row.id] || {{}};
      const schemaTables = ((row.schema || {{}}).tables || []);
      els.detail.innerHTML = `
        <div class="actions">
          <button class="approve" data-decision="approve">Approve</button>
          <button class="reject" data-decision="reject">Reject</button>
          <button class="flag" data-decision="flag">Flag</button>
          <span class="meta">Fingerprint: ${{escapeHtml(row.review_fingerprint)}}</span>
        </div>
        <textarea id="reason" rows="2" placeholder="Reason">${{escapeHtml(current.reason || '')}}</textarea>
        <textarea id="note" rows="3" placeholder="Reviewer note">${{escapeHtml(current.note || '')}}</textarea>
        <div class="section"><h2>Instruction</h2><pre>${{escapeHtml(row.instruction)}}</pre></div>
        <div class="section"><h2>Schema Summary</h2><pre>${{escapeHtml(row.schema_summary)}}</pre></div>
        <div class="section"><h2>Tables</h2>${{schemaTables.map(table => `<h3>${{escapeHtml(table.name)}}</h3>${{renderTable(table.rows || [])}}`).join('')}}</div>
        <div class="section"><h2>Gold SQL</h2><pre>${{escapeHtml(row.gold_sql)}}</pre></div>
        <div class="section"><h2>Expected Result</h2>${{renderTable(row.expected_result || [])}}</div>
        <div class="section"><h2>Judge</h2><pre>${{escapeHtml(JSON.stringify(judge, null, 2))}}</pre></div>
        <div class="section"><h2>Metadata</h2><pre>${{escapeHtml(JSON.stringify({{domain: row.domain, difficulty: row.difficulty, skills: row.skills, generation: row.generation}}, null, 2))}}</pre></div>
      `;
      els.detail.querySelectorAll('button[data-decision]').forEach(button => {{
        button.addEventListener('click', () => {{
          decisions[row.id] = {{
            row_id: row.id,
            fingerprint: row.review_fingerprint,
            decision: button.dataset.decision,
            reason: document.getElementById('reason').value,
            note: document.getElementById('note').value
          }};
          save();
          render();
        }});
      }});
      ['reason', 'note'].forEach(id => {{
        document.getElementById(id).addEventListener('input', () => {{
          if (!decisions[row.id]) return;
          decisions[row.id][id] = document.getElementById(id).value;
          save();
        }});
      }});
    }}
    function save() {{
      localStorage.setItem(packet.packet_id + ':decisions', JSON.stringify(decisions));
    }}
    function exportDecisions() {{
      const payload = {{
        packet_id: packet.packet_id,
        reviewer: els.reviewer.value || 'reviewer',
        exported_at: new Date().toISOString(),
        decisions: Object.values(decisions)
      }};
      const blob = new Blob([JSON.stringify(payload, null, 2)], {{type: 'application/json'}});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = packet.packet_id + '_decisions.json';
      a.click();
      URL.revokeObjectURL(url);
    }}
    function render() {{
      renderList();
      renderDetail();
    }}
    fillSelect(els.domain, 'All domains', uniq(rows.map(row => row.domain)));
    fillSelect(els.difficulty, 'All difficulty', uniq(rows.map(row => row.difficulty)));
    fillSelect(els.skill, 'All skills', uniq(rows.flatMap(row => row.skills || [])));
    fillSelect(els.status, 'All status', ['pending', 'approve', 'reject', 'flag']);
    els.reviewer.value = localStorage.getItem(packet.packet_id + ':reviewer') || '';
    els.reviewer.addEventListener('input', () => localStorage.setItem(packet.packet_id + ':reviewer', els.reviewer.value));
    Object.values(els).forEach(el => {{
      if (el && ['INPUT', 'SELECT'].includes(el.tagName)) el.addEventListener('input', render);
    }});
    els.bulkApprove.addEventListener('click', () => {{
      filteredRows().forEach(row => {{
        decisions[row.id] = {{
          row_id: row.id,
          fingerprint: row.review_fingerprint,
          decision: 'approve',
          reason: '',
          note: ''
        }};
      }});
      save();
      render();
    }});
    els.exportDecisions.addEventListener('click', exportDecisions);
    render();
  </script>
</body>
</html>
"""


def build_review_packets(
    *,
    storage: StorageClient,
    run_id: str,
    input_uri: str,
    out_uri: str,
    max_rows: int = 1000,
    overwrite: bool = False,
) -> dict[str, Any]:
    rows = load_rows(storage, input_uri)
    storage.ensure_dir(out_uri)
    packets = []
    for index in range(0, len(rows), max_rows):
        packet_number = len(packets) + 1
        packet_id = f"review_packet_{packet_number:04d}"
        packet_rows = rows[index : index + max_rows]
        packet_uri = join_uri(out_uri, f"{packet_id}.html")
        result = storage.write_text(
            packet_uri,
            build_review_html(packet_id, run_id, packet_rows),
            overwrite=overwrite,
        )
        packets.append(
            {
                "packet_id": packet_id,
                "uri": packet_uri,
                "artifact_id": result.artifact_id,
                "row_count": len(packet_rows),
                "first_row_id": packet_rows[0].get("id") if packet_rows else None,
                "last_row_id": packet_rows[-1].get("id") if packet_rows else None,
            }
        )
    manifest = {
        "run_id": run_id,
        "created_at": utc_now(),
        "input_uri": input_uri,
        "packet_count": len(packets),
        "row_count": len(rows),
        "packets": packets,
        "summary": summarize_rows(rows),
    }
    write_json(storage, join_uri(out_uri, "review_manifest.json"), manifest, overwrite=overwrite)
    return manifest


def _load_decisions(storage: StorageClient, decisions_uri: str) -> list[dict[str, Any]]:
    records = read_json_records(storage, decisions_uri)
    decisions = []
    for record in records:
        if "decisions" in record and isinstance(record["decisions"], list):
            for decision in record["decisions"]:
                if isinstance(decision, dict):
                    decisions.append(decision)
        else:
            decisions.append(record)
    return decisions


def _validate_decision(decision: dict[str, Any]) -> None:
    if decision.get("decision") not in VALID_DECISIONS:
        raise ValueError(f"invalid review decision for {decision.get('row_id')}: {decision.get('decision')}")
    if not decision.get("row_id"):
        raise ValueError("review decision missing row_id")
    if not decision.get("fingerprint"):
        raise ValueError(f"review decision missing fingerprint for {decision.get('row_id')}")


def apply_review_decisions(
    *,
    storage: StorageClient,
    run_id: str,
    accepted_uri: str,
    decisions_uri: str,
    out_uri: str,
    default: str = "pending",
    overwrite: bool = False,
) -> dict[str, Any]:
    if default not in {"pending", "approve-unreviewed"}:
        raise ValueError("--default must be pending or approve-unreviewed")
    accepted_rows = load_rows(storage, accepted_uri)
    decision_entries = storage.list(decisions_uri)
    decisions = _load_decisions(storage, decisions_uri)
    by_id: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        _validate_decision(decision)
        by_id[str(decision["row_id"])] = decision

    approved = []
    rejected = []
    pending = []
    errors = []
    accepted_by_id = {str(row.get("id")): row for row in accepted_rows}
    for row_id in by_id:
        if row_id not in accepted_by_id:
            errors.append(f"decision references unknown accepted row: {row_id}")

    for row in accepted_rows:
        row_id = str(row.get("id"))
        fingerprint = row_fingerprint(row)
        decision = by_id.get(row_id)
        payload = dict(row)
        if decision:
            if str(decision.get("fingerprint")) != fingerprint:
                errors.append(f"fingerprint mismatch for {row_id}")
                continue
            payload["review"] = {
                "decision": decision["decision"],
                "reason": decision.get("reason", ""),
                "note": decision.get("note", ""),
                "fingerprint": fingerprint,
            }
            if decision["decision"] == "approve":
                approved.append(payload)
            elif decision["decision"] == "reject":
                rejected.append(payload)
            else:
                pending.append(payload)
        elif default == "approve-unreviewed":
            payload["review"] = {"decision": "approve", "reason": "default approve-unreviewed", "note": ""}
            approved.append(payload)
        else:
            payload["review"] = {"decision": "pending", "reason": "", "note": ""}
            pending.append(payload)

    if errors:
        raise ValueError("; ".join(errors))

    storage.ensure_dir(out_uri)
    approved_result = write_jsonl(storage, join_uri(out_uri, "approved.jsonl"), approved, overwrite=overwrite)
    rejected_result = write_jsonl(
        storage,
        join_uri(out_uri, "rejected_by_human.jsonl"),
        rejected,
        overwrite=overwrite,
    )
    pending_result = write_jsonl(storage, join_uri(out_uri, "pending_review.jsonl"), pending, overwrite=overwrite)
    summary = {
        "run_id": run_id,
        "created_at": utc_now(),
        "accepted_uri": accepted_uri,
        "decisions_uri": decisions_uri,
        "approved_count": len(approved),
        "rejected_by_human_count": len(rejected),
        "pending_review_count": len(pending),
        "decision_artifact_ids": [
            entry.artifact_id
            for entry in decision_entries
            if not entry.is_dir and entry.artifact_id is not None
        ],
        "artifacts": {
            "approved": approved_result.artifact_id,
            "rejected_by_human": rejected_result.artifact_id,
            "pending_review": pending_result.artifact_id,
        },
    }
    write_json(storage, join_uri(out_uri, "review_summary.json"), summary, overwrite=overwrite)
    return summary


def create_signoff(
    *,
    storage: StorageClient,
    run_id: str,
    reviewed_uri: str,
    reviewer: str,
    out_uri: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    approved_uri = join_uri(reviewed_uri, "approved.jsonl")
    rejected_uri = join_uri(reviewed_uri, "rejected_by_human.jsonl")
    pending_uri = join_uri(reviewed_uri, "pending_review.jsonl")
    summary_uri = join_uri(reviewed_uri, "review_summary.json")
    approved = load_rows(storage, approved_uri) if storage.exists(approved_uri) else []
    rejected = load_rows(storage, rejected_uri) if storage.exists(rejected_uri) else []
    pending = load_rows(storage, pending_uri) if storage.exists(pending_uri) else []
    review_summary = json.loads(storage.read_text(summary_uri)) if storage.exists(summary_uri) else {}
    reviewed_artifacts = review_summary.get("artifacts", {}) if isinstance(review_summary, dict) else {}
    signoff = {
        "run_id": run_id,
        "reviewer": reviewer,
        "signed_at": utc_now(),
        "approved_row_count": len(approved),
        "rejected_row_count": len(rejected),
        "pending_row_count": len(pending),
        "source_approved_uri": approved_uri,
        "source_accepted_artifact_ids": [
            artifact_id
            for artifact_id in [reviewed_artifacts.get("approved")]
            if artifact_id
        ],
        "review_decision_artifact_ids": review_summary.get("decision_artifact_ids", [])
        if isinstance(review_summary, dict)
        else [],
        "reviewed_uri": reviewed_uri,
        "gate_version": GATE_VERSION,
        "export_format": "sft_sql_only",
        "fine_tune_permission": True,
    }
    write_json(storage, out_uri, signoff, overwrite=overwrite)
    return signoff


def load_signoff(storage: StorageClient, signoff_uri: str) -> dict[str, Any]:
    payload = json.loads(storage.read_text(signoff_uri))
    if not payload.get("fine_tune_permission"):
        raise ValueError("signoff does not grant fine-tune permission")
    return payload


def schema_fingerprint(row: dict[str, Any]) -> str:
    schema = row.get("schema", {})
    tables = []
    if isinstance(schema, dict):
        for table in schema.get("tables", []):
            if not isinstance(table, dict):
                continue
            columns = [
                (column.get("name"), column.get("type", "TEXT"))
                for column in table.get("columns", [])
                if isinstance(column, dict)
            ]
            tables.append((table.get("name"), columns))
    return json.dumps(tables, sort_keys=True)


def split_rows_by_schema(
    rows: list[dict[str, Any]],
    *,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> dict[str, list[dict[str, Any]]]:
    total = train_ratio + val_ratio + test_ratio
    if abs(total - 1.0) > 1e-6:
        raise ValueError("train, val, and test ratios must sum to 1.0")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[schema_fingerprint(row)].append(row)
    ordered_groups = [groups[key] for key in sorted(groups)]
    splits = {"train": [], "validation": [], "test": []}
    row_total = len(rows)
    train_target = row_total * train_ratio
    val_target = row_total * val_ratio
    for group in ordered_groups:
        if len(splits["train"]) < train_target:
            splits["train"].extend(group)
        elif len(splits["validation"]) < val_target:
            splits["validation"].extend(group)
        else:
            splits["test"].extend(group)
    return splits


def export_sft_dataset(
    *,
    storage: StorageClient,
    input_uri: str,
    out_uri: str,
    signoff_uri: str | None,
    unsafe_skip_review_signoff: bool = False,
    train_ratio: float = 0.9,
    val_ratio: float = 0.05,
    test_ratio: float = 0.05,
    overwrite: bool = False,
) -> dict[str, Any]:
    if not signoff_uri and not unsafe_skip_review_signoff:
        raise ValueError("--signoff is required unless --unsafe-skip-review-signoff is passed")
    signoff = None
    if signoff_uri:
        signoff = load_signoff(storage, signoff_uri)
    rows = load_rows(storage, input_uri)
    splits = split_rows_by_schema(
        rows,
        train_ratio=train_ratio,
        val_ratio=val_ratio,
        test_ratio=test_ratio,
    )
    storage.ensure_dir(out_uri)
    artifacts = {}
    counts = {}
    for split_name, split_rows in splits.items():
        records = [row_to_sft_record(row) for row in split_rows]
        result = write_jsonl(storage, join_uri(out_uri, f"{split_name}.jsonl"), records, overwrite=overwrite)
        artifacts[split_name] = result.artifact_id
        counts[split_name] = len(records)
    manifest = {
        "created_at": utc_now(),
        "input_uri": input_uri,
        "signoff_uri": signoff_uri,
        "unsafe_skip_review_signoff": unsafe_skip_review_signoff,
        "format": "sft_sql_only",
        "counts": counts,
        "summary": summarize_rows(rows),
        "artifacts": artifacts,
        "signoff": signoff,
    }
    write_json(storage, join_uri(out_uri, "dataset_manifest.json"), manifest, overwrite=overwrite)
    return manifest
