CREATE TABLE IF NOT EXISTS public.ops_alert_queue (
    alert_id uuid PRIMARY KEY,
    card_id uuid NOT NULL REFERENCES public.priority_cards(card_id) ON DELETE CASCADE,
    evaluation_run_id uuid,
    manufacturer_id text,
    substation_id integer,
    priority_rank integer,
    freshness_status text,
    priority_level text NOT NULL CHECK (priority_level IN ('urgent', 'high')),
    priority_score double precision,
    status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'acked', 'resolved')),
    enqueue_reason text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    acked_at timestamptz,
    acked_by text
);

CREATE UNIQUE INDEX IF NOT EXISTS ops_alert_queue_evaluation_substation_uidx
ON public.ops_alert_queue(evaluation_run_id, manufacturer_id, substation_id)
WHERE evaluation_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ops_alert_queue_evaluation_idx
ON public.ops_alert_queue(evaluation_run_id, status, priority_score DESC);

CREATE TABLE IF NOT EXISTS public.agent_runs (
    run_id uuid PRIMARY KEY,
    alert_id uuid NOT NULL REFERENCES public.ops_alert_queue(alert_id) ON DELETE CASCADE,
    card_id uuid NOT NULL REFERENCES public.priority_cards(card_id) ON DELETE CASCADE,
    evaluation_run_id uuid,
    manufacturer_id text,
    substation_id integer,
    parent_run_id uuid REFERENCES public.agent_runs(run_id),
    trigger_type text NOT NULL DEFAULT 'alert',
    requested_by text,
    trigger_reason text,
    approved_action_task_id uuid,
    status text NOT NULL CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    agent_mode text CHECK (agent_mode IN ('llm', 'fallback')),
    ops_output jsonb,
    token_usage jsonb,
    loop_summary jsonb,
    review_status text NOT NULL DEFAULT 'pending'
        CHECK (review_status IN ('pending', 'approved', 'rejected', 'corrected')),
    review_task_id uuid,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.agent_run_events (
    event_id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES public.agent_runs(run_id) ON DELETE CASCADE,
    event_type text NOT NULL,
    message text NOT NULL,
    payload jsonb,
    operation_key text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_run_events_run_idx
ON public.agent_run_events(run_id, event_id);

CREATE UNIQUE INDEX IF NOT EXISTS agent_run_events_operation_key_uidx
ON public.agent_run_events(operation_key) WHERE operation_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.agent_run_artifacts (
    artifact_id uuid PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES public.agent_runs(run_id) ON DELETE CASCADE,
    kind text NOT NULL,
    name text NOT NULL,
    uri text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS agent_run_artifact_run_name_idx
ON public.agent_run_artifacts(run_id, name);

CREATE TABLE IF NOT EXISTS public.agent_run_actions (
    run_id uuid NOT NULL REFERENCES public.agent_runs(run_id) ON DELETE CASCADE,
    action_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    requested_by text,
    artifact_id uuid REFERENCES public.agent_run_artifacts(artifact_id) ON DELETE SET NULL,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, action_name)
);

CREATE TABLE IF NOT EXISTS public.agent_loop_iterations (
    iteration_id bigserial PRIMARY KEY,
    run_id uuid NOT NULL,
    iteration integer NOT NULL,
    phase text NOT NULL,
    decision text NOT NULL,
    confidence double precision NOT NULL,
    evidence_score double precision NOT NULL,
    missing_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    model_verification jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_loop_iterations_run_idx
ON public.agent_loop_iterations(run_id, iteration_id);

CREATE UNIQUE INDEX IF NOT EXISTS agent_loop_iterations_run_iteration_phase_uidx
ON public.agent_loop_iterations(run_id, iteration, phase);

CREATE TABLE IF NOT EXISTS public.evidence_candidates (
    candidate_id uuid PRIMARY KEY,
    run_id uuid,
    source_type text NOT NULL,
    source_uri text,
    title text NOT NULL,
    content text NOT NULL,
    query text,
    risk_level text NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    trust_score double precision NOT NULL CHECK (trust_score >= 0 AND trust_score <= 1),
    status text NOT NULL CHECK (
        status IN ('pending', 'auto_approved', 'approved', 'rejected', 'ingest_failed')
    ),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    requested_by text NOT NULL,
    reviewed_by text,
    review_reason text,
    rag_document_id text,
    rag_chunk_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz
);

CREATE TABLE IF NOT EXISTS public.human_review_tasks (
    task_id uuid PRIMARY KEY,
    task_type text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('pending', 'auto_approved', 'approved', 'rejected', 'corrected', 'cancelled')
    ),
    risk_level text NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    title text NOT NULL,
    run_id uuid,
    candidate_id uuid REFERENCES public.evidence_candidates(candidate_id) ON DELETE SET NULL,
    retrain_job_id uuid,
    model_candidate_id uuid,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    resolution jsonb NOT NULL DEFAULT '{}'::jsonb,
    assigned_to text,
    reviewed_by text,
    operation_key text,
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz
);

CREATE UNIQUE INDEX IF NOT EXISTS human_review_tasks_operation_key_uidx
ON public.human_review_tasks(operation_key) WHERE operation_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.training_feedback (
    feedback_id uuid PRIMARY KEY,
    task_id uuid NOT NULL UNIQUE
        REFERENCES public.human_review_tasks(task_id) ON DELETE CASCADE,
    run_id uuid,
    card_id uuid,
    reviewer text NOT NULL,
    decision text NOT NULL,
    original_output jsonb NOT NULL DEFAULT '{}'::jsonb,
    corrected_output jsonb NOT NULL DEFAULT '{}'::jsonb,
    corrected_label text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.automation_policy (
    policy_id text PRIMARY KEY,
    mode text NOT NULL CHECK (mode IN ('human_only', 'assisted', 'guarded_auto')),
    auto_transition_enabled boolean NOT NULL DEFAULT false,
    minimum_review_count integer NOT NULL DEFAULT 100,
    minimum_approval_rate double precision NOT NULL DEFAULT 0.95,
    minimum_confidence double precision NOT NULL DEFAULT 0.90,
    minimum_source_trust double precision NOT NULL DEFAULT 0.85,
    maximum_drift_score double precision NOT NULL DEFAULT 0.10,
    final_review_required boolean NOT NULL DEFAULT true,
    updated_by text NOT NULL DEFAULT 'system',
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO public.automation_policy(policy_id, mode)
VALUES ('default', 'human_only')
ON CONFLICT (policy_id) DO NOTHING;

CREATE INDEX IF NOT EXISTS evidence_candidates_status_idx
ON public.evidence_candidates(status, created_at DESC);
CREATE INDEX IF NOT EXISTS review_tasks_status_idx
ON public.human_review_tasks(status, created_at DESC);
CREATE INDEX IF NOT EXISTS training_feedback_created_idx
ON public.training_feedback(created_at DESC);

CREATE TABLE IF NOT EXISTS public.retrain_jobs (
    job_id uuid PRIMARY KEY,
    status text NOT NULL CHECK (
        status IN ('pending_approval', 'approved', 'running', 'completed', 'failed',
                   'rejected', 'cancelled')
    ),
    requested_by text NOT NULL,
    reason text NOT NULL,
    feedback_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
    dataset_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    execution_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    approved_by text,
    approval_reason text,
    error text,
    model_candidate_id uuid,
    auto_start_when_approved boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_at timestamptz,
    started_at timestamptz,
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS public.model_candidates (
    candidate_id uuid PRIMARY KEY,
    job_id uuid NOT NULL REFERENCES public.retrain_jobs(job_id) ON DELETE CASCADE,
    version text NOT NULL,
    artifact_uri text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('awaiting_validation', 'awaiting_promotion', 'promoted', 'rejected')
    ),
    baseline_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    candidate_metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    validation_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    promoted_by text,
    promotion_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    promoted_at timestamptz
);

CREATE TABLE IF NOT EXISTS public.model_deployments (
    deployment_id uuid PRIMARY KEY,
    candidate_id uuid NOT NULL REFERENCES public.model_candidates(candidate_id),
    version text NOT NULL,
    artifact_uri text NOT NULL,
    active boolean NOT NULL DEFAULT true,
    promoted_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS retrain_jobs_status_idx
ON public.retrain_jobs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS model_candidates_status_idx
ON public.model_candidates(status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS model_deployments_one_active_idx
ON public.model_deployments(active) WHERE active;
