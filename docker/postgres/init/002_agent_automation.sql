create table if not exists agent_runs (
    run_id uuid primary key,
    alert_id uuid not null references ops_alert_queue(alert_id) on delete cascade,
    card_id uuid not null references priority_cards(card_id) on delete cascade,
    evaluation_run_id uuid,
    manufacturer_id text,
    substation_id integer,
    parent_run_id uuid references agent_runs(run_id),
    trigger_type text not null default 'alert',
    requested_by text,
    trigger_reason text,
    approved_action_task_id uuid,
    status text not null check (status in ('queued', 'running', 'completed', 'failed')),
    agent_mode text check (agent_mode in ('llm', 'fallback')),
    ops_output jsonb,
    token_usage jsonb,
    loop_summary jsonb,
    review_status text not null default 'pending'
        check (review_status in ('pending', 'approved', 'rejected', 'corrected')),
    review_task_id uuid,
    error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table agent_runs add column if not exists parent_run_id uuid references agent_runs(run_id);
alter table agent_runs add column if not exists trigger_type text not null default 'alert';
alter table agent_runs add column if not exists requested_by text;
alter table agent_runs add column if not exists trigger_reason text;
alter table agent_runs add column if not exists approved_action_task_id uuid;

create table if not exists agent_run_events (
    event_id bigserial primary key,
    run_id uuid not null references agent_runs(run_id) on delete cascade,
    event_type text not null,
    message text not null,
    payload jsonb,
    created_at timestamptz not null default now()
);

create index if not exists agent_run_events_run_idx
    on agent_run_events(run_id, event_id);

create table if not exists agent_run_artifacts (
    artifact_id uuid primary key,
    run_id uuid not null references agent_runs(run_id) on delete cascade,
    kind text not null,
    name text not null,
    uri text not null,
    created_at timestamptz not null default now(),
    unique (run_id, name)
);

create table if not exists agent_run_actions (
    run_id uuid not null references agent_runs(run_id) on delete cascade,
    action_name text not null,
    status text not null check (status in ('running', 'completed', 'failed')),
    requested_by text,
    artifact_id uuid references agent_run_artifacts(artifact_id) on delete set null,
    error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (run_id, action_name)
);
