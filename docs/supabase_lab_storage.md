# Supabase Lab Storage

Data Forge Lab supports two run-state backends:

- `local`: JSON files under `generation/lab/runs`, useful for offline development.
- `supabase`: hosted run state for user-facing deployments.

The UI should never talk to Supabase with a service-role key. The browser calls the Data Forge Lab API, and the server writes to Supabase.

## Schema

Apply the migration in:

```text
supabase/migrations/20260603000000_data_forge_lab.sql
```

It creates:

- `data_forge_lab_runs`: canonical run snapshot and current step index.
- `data_forge_lab_events`: idempotent timeline/audit events.
- `data_forge_lab_artifacts`: report, dataset, checkpoint, and external artifact metadata.

Large files such as model checkpoints should be saved to a file backend such as local disk, Supabase Storage, Google Drive, or Hugging Face. The database stores manifests and pointers.

## Environment

For local JSON storage:

```bash
export DATA_FORGE_LAB_STORE=local
```

For Supabase-backed runs:

```bash
export DATA_FORGE_LAB_STORE=supabase
export SUPABASE_URL=https://<project-ref>.supabase.co
export SUPABASE_SERVICE_ROLE_KEY=<server-only-service-role-key>
```

Then run:

```bash
PYTHONPATH=src python3 -m data_forge.cli lab serve
```

## Security

- Use `SUPABASE_SERVICE_ROLE_KEY` only on the server.
- Do not put Supabase service keys in static HTML, client JavaScript, GitHub Pages, or Hugging Face Spaces public variables.
- For a public hosted app, put the Lab API behind auth before allowing real training jobs or paid generator calls.
