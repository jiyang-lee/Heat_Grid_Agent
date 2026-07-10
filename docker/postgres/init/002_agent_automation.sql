create table if not exists model_feature_snapshots (
    window_id uuid primary key,
    feature_set_version text not null,
    features jsonb not null,
    source_artifacts jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists agent_loop_iterations (
    iteration_id bigserial primary key,
    run_id uuid not null,
    iteration integer not null,
    phase text not null,
    decision text not null,
    confidence double precision not null,
    evidence_score double precision not null,
    missing_evidence jsonb not null default '[]'::jsonb,
    model_verification jsonb,
    created_at timestamptz not null default now()
);

create index if not exists agent_loop_iterations_run_idx
    on agent_loop_iterations(run_id, iteration_id);

create table if not exists evidence_candidates (
    candidate_id uuid primary key,
    run_id uuid,
    source_type text not null,
    source_uri text,
    title text not null,
    content text not null,
    query text,
    risk_level text not null check (risk_level in ('low', 'medium', 'high', 'critical')),
    trust_score double precision not null check (trust_score >= 0 and trust_score <= 1),
    status text not null check (
        status in ('pending', 'auto_approved', 'approved', 'rejected', 'ingest_failed')
    ),
    metadata jsonb not null default '{}'::jsonb,
    requested_by text not null,
    reviewed_by text,
    review_reason text,
    rag_document_id text,
    rag_chunk_id text,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz
);

create table if not exists human_review_tasks (
    task_id uuid primary key,
    task_type text not null,
    status text not null check (
        status in ('pending', 'auto_approved', 'approved', 'rejected', 'corrected', 'cancelled')
    ),
    risk_level text not null check (risk_level in ('low', 'medium', 'high', 'critical')),
    title text not null,
    run_id uuid,
    candidate_id uuid references evidence_candidates(candidate_id) on delete set null,
    retrain_job_id uuid,
    model_candidate_id uuid,
    payload jsonb not null default '{}'::jsonb,
    resolution jsonb not null default '{}'::jsonb,
    assigned_to text,
    reviewed_by text,
    created_at timestamptz not null default now(),
    reviewed_at timestamptz
);

create table if not exists training_feedback (
    feedback_id uuid primary key,
    task_id uuid not null references human_review_tasks(task_id) on delete cascade,
    run_id uuid,
    card_id uuid,
    reviewer text not null,
    decision text not null,
    original_output jsonb not null default '{}'::jsonb,
    corrected_output jsonb not null default '{}'::jsonb,
    corrected_label text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (task_id)
);

create table if not exists automation_policy (
    policy_id text primary key,
    mode text not null check (mode in ('human_only', 'assisted', 'guarded_auto')),
    auto_transition_enabled boolean not null default false,
    minimum_review_count integer not null default 100,
    minimum_approval_rate double precision not null default 0.95,
    minimum_confidence double precision not null default 0.90,
    minimum_source_trust double precision not null default 0.85,
    maximum_drift_score double precision not null default 0.10,
    final_review_required boolean not null default true,
    updated_by text not null default 'system',
    updated_at timestamptz not null default now()
);

insert into automation_policy (policy_id, mode)
values ('default', 'human_only')
on conflict (policy_id) do nothing;

create table if not exists retrain_jobs (
    job_id uuid primary key,
    status text not null check (
        status in ('pending_approval', 'approved', 'running', 'completed', 'failed',
                   'rejected', 'cancelled')
    ),
    requested_by text not null,
    reason text not null,
    feedback_ids jsonb not null default '[]'::jsonb,
    dataset_snapshot jsonb not null default '{}'::jsonb,
    execution_metadata jsonb not null default '{}'::jsonb,
    approved_by text,
    approval_reason text,
    error text,
    model_candidate_id uuid,
    auto_start_when_approved boolean not null default false,
    created_at timestamptz not null default now(),
    approved_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz
);

create table if not exists model_candidates (
    candidate_id uuid primary key,
    job_id uuid not null references retrain_jobs(job_id) on delete cascade,
    version text not null,
    artifact_uri text not null,
    status text not null check (
        status in ('awaiting_validation', 'awaiting_promotion', 'promoted', 'rejected')
    ),
    baseline_metrics jsonb not null default '{}'::jsonb,
    candidate_metrics jsonb not null default '{}'::jsonb,
    validation_summary jsonb not null default '{}'::jsonb,
    promoted_by text,
    promotion_reason text,
    created_at timestamptz not null default now(),
    promoted_at timestamptz
);

create table if not exists model_deployments (
    deployment_id uuid primary key,
    candidate_id uuid not null references model_candidates(candidate_id),
    version text not null,
    artifact_uri text not null,
    active boolean not null default true,
    promoted_by text not null,
    created_at timestamptz not null default now()
);

create index if not exists evidence_candidates_status_idx
    on evidence_candidates(status, created_at desc);
create index if not exists review_tasks_status_idx
    on human_review_tasks(status, created_at desc);
create index if not exists training_feedback_created_idx
    on training_feedback(created_at desc);
create index if not exists retrain_jobs_status_idx
    on retrain_jobs(status, created_at desc);
create index if not exists model_candidates_status_idx
    on model_candidates(status, created_at desc);
create unique index if not exists model_deployments_one_active_idx
    on model_deployments(active) where active;
