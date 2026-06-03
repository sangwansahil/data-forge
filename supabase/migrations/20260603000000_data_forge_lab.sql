create table if not exists public.data_forge_lab_runs (
  run_id text primary key,
  title text not null,
  user_prompt text not null,
  status text not null,
  task_type text not null,
  benchmark text not null,
  current_step_index integer not null default 1,
  payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.data_forge_lab_events (
  event_id text primary key,
  run_id text not null references public.data_forge_lab_runs(run_id) on delete cascade,
  event_type text not null,
  payload jsonb not null,
  created_at timestamptz not null default now()
);

create table if not exists public.data_forge_lab_artifacts (
  artifact_id text primary key,
  run_id text not null references public.data_forge_lab_runs(run_id) on delete cascade,
  label text not null,
  uri text not null,
  kind text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists data_forge_lab_runs_updated_at_idx
  on public.data_forge_lab_runs(updated_at desc);

create index if not exists data_forge_lab_events_run_id_created_at_idx
  on public.data_forge_lab_events(run_id, created_at asc);

create index if not exists data_forge_lab_artifacts_run_id_created_at_idx
  on public.data_forge_lab_artifacts(run_id, created_at asc);

alter table public.data_forge_lab_runs enable row level security;
alter table public.data_forge_lab_events enable row level security;
alter table public.data_forge_lab_artifacts enable row level security;

create policy "service role manages lab runs"
  on public.data_forge_lab_runs
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

create policy "service role manages lab events"
  on public.data_forge_lab_events
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');

create policy "service role manages lab artifacts"
  on public.data_forge_lab_artifacts
  for all
  using (auth.role() = 'service_role')
  with check (auth.role() = 'service_role');
