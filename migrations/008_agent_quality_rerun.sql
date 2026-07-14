COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 008';

DO $preflight$
BEGIN
    IF EXISTS (SELECT 1 FROM public.windows WHERE substation_id IS NULL) THEN
        RAISE EXCEPTION 'v008 preflight failed: windows.substation_id contains NULL';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM public.agent_run_tasks
        WHERE task_key IN ('agent_graph:v1', 'agent_graph:v2')
        GROUP BY run_id
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'v008 preflight failed: a run has multiple graph tasks';
    END IF;
END
$preflight$;

ALTER TABLE public.windows ALTER COLUMN substation_id SET NOT NULL;
ALTER TABLE public.model_outputs ALTER COLUMN display_rank SET DEFAULT 100;
ALTER TABLE public.sensor_summaries ALTER COLUMN display_rank SET DEFAULT 100;
ALTER TABLE public.agent_budget_ledger DROP CONSTRAINT IF EXISTS agent_budget_ledger_check;

ALTER SEQUENCE public.agent_run_events_event_id_seq OWNED BY NONE;
CREATE TABLE public.agent_run_events_v008 (
    event_id bigint NOT NULL DEFAULT nextval('public.agent_run_events_event_id_seq'::regclass),
    run_id uuid NOT NULL,
    event_type text NOT NULL,
    message text NOT NULL,
    payload jsonb,
    operation_key text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT agent_run_events_v008_pkey PRIMARY KEY (event_id)
);
INSERT INTO public.agent_run_events_v008 (
    event_id, run_id, event_type, message, payload, operation_key, created_at
)
SELECT event_id, run_id, event_type, message, payload, operation_key, created_at
FROM public.agent_run_events;
DROP TABLE public.agent_run_events;
ALTER TABLE public.agent_run_events_v008 RENAME TO agent_run_events;
ALTER TABLE public.agent_run_events
    RENAME CONSTRAINT agent_run_events_v008_pkey TO agent_run_events_pkey;
ALTER SEQUENCE public.agent_run_events_event_id_seq OWNED BY public.agent_run_events.event_id;
ALTER TABLE public.agent_run_events ADD CONSTRAINT agent_run_events_run_id_fkey
    FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT;
CREATE INDEX agent_run_events_run_idx ON public.agent_run_events(run_id, event_id);
CREATE UNIQUE INDEX agent_run_events_operation_key_uidx
    ON public.agent_run_events(operation_key) WHERE operation_key IS NOT NULL;
CREATE INDEX agent_run_events_v3_snapshot_idx
    ON public.agent_run_events(run_id, event_type, event_id DESC);

ALTER TABLE public.agent_runs DROP CONSTRAINT IF EXISTS agent_runs_review_task_id_fkey;
ALTER TABLE public.agent_run_reviews
    DROP CONSTRAINT IF EXISTS agent_run_reviews_review_task_id_fkey;
ALTER TABLE public.training_feedback
    DROP CONSTRAINT IF EXISTS training_feedback_task_id_fkey;

CREATE TABLE public.human_review_tasks_v008 (
    task_id uuid PRIMARY KEY,
    task_type text NOT NULL,
    status text NOT NULL CHECK (
        status IN ('pending', 'auto_approved', 'approved', 'rejected', 'corrected', 'cancelled')
    ),
    risk_level text NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    title text NOT NULL,
    run_id uuid,
    candidate_id uuid,
    retrain_job_id uuid,
    model_candidate_id uuid,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    resolution jsonb NOT NULL DEFAULT '{}'::jsonb,
    assigned_to text,
    reviewed_by text,
    operation_key text,
    subject_type text NOT NULL,
    subject_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    reviewed_at timestamptz,
    CONSTRAINT human_review_tasks_subject_check CHECK (
        (subject_type = 'agent_run' AND run_id IS NOT NULL AND subject_key = run_id::text)
        OR (subject_type <> 'agent_run' AND run_id IS NULL)
    )
);
INSERT INTO public.human_review_tasks_v008 (
    task_id, task_type, status, risk_level, title, run_id, candidate_id,
    retrain_job_id, model_candidate_id, payload, resolution, assigned_to,
    reviewed_by, operation_key, subject_type, subject_key, created_at, reviewed_at
)
SELECT
    task_id, task_type, status, risk_level, title, run_id, candidate_id,
    retrain_job_id, model_candidate_id, payload, resolution, assigned_to,
    reviewed_by, operation_key, subject_type, subject_key, created_at, reviewed_at
FROM public.human_review_tasks;
DROP TABLE public.human_review_tasks;
ALTER TABLE public.human_review_tasks_v008 RENAME TO human_review_tasks;
ALTER TABLE public.human_review_tasks ADD CONSTRAINT human_review_tasks_run_id_fkey
    FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT;
ALTER TABLE public.human_review_tasks ADD CONSTRAINT human_review_tasks_candidate_id_fkey
    FOREIGN KEY (candidate_id) REFERENCES public.evidence_candidates(candidate_id) ON DELETE SET NULL;
ALTER TABLE public.human_review_tasks ADD CONSTRAINT human_review_tasks_retrain_job_id_fkey
    FOREIGN KEY (retrain_job_id) REFERENCES public.retrain_jobs(job_id) ON DELETE RESTRICT;
ALTER TABLE public.human_review_tasks ADD CONSTRAINT human_review_tasks_model_candidate_id_fkey
    FOREIGN KEY (model_candidate_id) REFERENCES public.model_candidates(candidate_id) ON DELETE RESTRICT;
CREATE UNIQUE INDEX human_review_tasks_operation_key_uidx
    ON public.human_review_tasks(operation_key) WHERE operation_key IS NOT NULL;
CREATE INDEX review_tasks_status_idx
    ON public.human_review_tasks(status, created_at DESC);
ALTER TABLE public.agent_runs ADD CONSTRAINT agent_runs_review_task_id_fkey
    FOREIGN KEY (review_task_id) REFERENCES public.human_review_tasks(task_id) ON DELETE RESTRICT;
ALTER TABLE public.agent_run_reviews ADD CONSTRAINT agent_run_reviews_review_task_id_fkey
    FOREIGN KEY (review_task_id) REFERENCES public.human_review_tasks(task_id) ON DELETE RESTRICT;
ALTER TABLE public.training_feedback ADD CONSTRAINT training_feedback_task_id_fkey
    FOREIGN KEY (task_id) REFERENCES public.human_review_tasks(task_id) ON DELETE RESTRICT;

CREATE SEQUENCE IF NOT EXISTS public.priority_card_review_reasons_review_reason_id_seq;
ALTER SEQUENCE public.priority_card_review_reasons_review_reason_id_seq OWNED BY NONE;
CREATE TABLE public.priority_card_review_reasons_v008 (
    review_reason_id bigint NOT NULL DEFAULT nextval(
        'public.priority_card_review_reasons_review_reason_id_seq'::regclass
    ),
    card_id uuid NOT NULL,
    reason_code text NOT NULL,
    display_rank integer NOT NULL DEFAULT 100,
    CONSTRAINT priority_card_review_reasons_v008_pkey PRIMARY KEY (review_reason_id),
    CONSTRAINT priority_card_review_reasons_v008_card_reason_key UNIQUE (card_id, reason_code)
);
INSERT INTO public.priority_card_review_reasons_v008 (card_id, reason_code, display_rank)
SELECT card_id, reason_code, display_rank
FROM public.priority_card_review_reasons
ORDER BY card_id, reason_code;
DROP TABLE public.priority_card_review_reasons;
ALTER TABLE public.priority_card_review_reasons_v008 RENAME TO priority_card_review_reasons;
ALTER TABLE public.priority_card_review_reasons
    RENAME CONSTRAINT priority_card_review_reasons_v008_pkey
    TO priority_card_review_reasons_pkey;
ALTER TABLE public.priority_card_review_reasons
    RENAME CONSTRAINT priority_card_review_reasons_v008_card_reason_key
    TO priority_card_review_reasons_card_id_reason_code_key;
ALTER SEQUENCE public.priority_card_review_reasons_review_reason_id_seq
    OWNED BY public.priority_card_review_reasons.review_reason_id;
ALTER TABLE public.priority_card_review_reasons
    ADD CONSTRAINT priority_card_review_reasons_card_id_fkey
    FOREIGN KEY (card_id) REFERENCES public.priority_cards(card_id) ON DELETE CASCADE;

ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS root_run_id uuid;
ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS lineage_depth integer;
ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS source_review_id uuid;
ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS target_stage text;
ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS source_input_snapshot jsonb;
ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS input_schema_version text;
ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS input_hash text;
ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS input_snapshot_origin text;
ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS input_snapshot_status text;
ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS reconstructed_at timestamptz;

WITH RECURSIVE lineage AS (
    SELECT run_id, run_id AS root_run_id, 0 AS depth, ARRAY[run_id] AS path
    FROM public.agent_runs
    WHERE parent_run_id IS NULL
    UNION ALL
    SELECT child.run_id, lineage.root_run_id, lineage.depth + 1, lineage.path || child.run_id
    FROM public.agent_runs child
    JOIN lineage ON child.parent_run_id = lineage.run_id
    WHERE NOT child.run_id = ANY(lineage.path) AND lineage.depth < 2
)
UPDATE public.agent_runs run
SET root_run_id = lineage.root_run_id,
    lineage_depth = lineage.depth,
    input_snapshot_origin = 'legacy_v1',
    input_snapshot_status = 'unavailable'
FROM lineage
WHERE lineage.run_id = run.run_id;

DO $lineage_preflight$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.agent_runs
        WHERE root_run_id IS NULL OR lineage_depth IS NULL OR lineage_depth > 2
    ) THEN
        RAISE EXCEPTION 'v008 preflight failed: invalid or cyclic agent run lineage';
    END IF;
END
$lineage_preflight$;

ALTER TABLE public.agent_runs ALTER COLUMN root_run_id SET NOT NULL;
ALTER TABLE public.agent_runs ALTER COLUMN lineage_depth SET NOT NULL;
ALTER TABLE public.agent_runs ALTER COLUMN lineage_depth SET DEFAULT 0;
ALTER TABLE public.agent_runs ALTER COLUMN input_snapshot_origin SET NOT NULL;
ALTER TABLE public.agent_runs ALTER COLUMN input_snapshot_origin SET DEFAULT 'native_v2';
ALTER TABLE public.agent_runs ALTER COLUMN input_snapshot_status SET NOT NULL;
ALTER TABLE public.agent_runs ALTER COLUMN input_snapshot_status SET DEFAULT 'unavailable';
ALTER TABLE public.agent_runs ADD CONSTRAINT agent_runs_lineage_depth_check
    CHECK (lineage_depth BETWEEN 0 AND 2);
ALTER TABLE public.agent_runs ADD CONSTRAINT agent_runs_input_origin_check
    CHECK (input_snapshot_origin IN ('native_v2', 'legacy_reconstructed_v008', 'legacy_v1'));
ALTER TABLE public.agent_runs ADD CONSTRAINT agent_runs_input_status_check
    CHECK (input_snapshot_status IN ('available', 'unavailable'));
ALTER TABLE public.agent_runs ADD CONSTRAINT agent_runs_input_snapshot_check CHECK (
    (input_snapshot_status = 'available'
        AND source_input_snapshot IS NOT NULL
        AND jsonb_typeof(source_input_snapshot) = 'object'
        AND input_schema_version IS NOT NULL
        AND input_hash ~ '^[0-9a-f]{64}$')
    OR (input_snapshot_status = 'unavailable'
        AND source_input_snapshot IS NULL
        AND input_hash IS NULL)
);
ALTER TABLE public.agent_runs ADD CONSTRAINT agent_runs_root_run_id_fkey
    FOREIGN KEY (root_run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT;
ALTER TABLE public.agent_runs ADD CONSTRAINT agent_runs_source_review_id_fkey
    FOREIGN KEY (source_review_id) REFERENCES public.agent_run_reviews(review_id) ON DELETE RESTRICT;
ALTER TABLE public.agent_runs ADD CONSTRAINT agent_runs_target_stage_check CHECK (
    target_stage IS NULL OR target_stage IN (
        'ml_validation', 'weather_context', 'rag_retrieval', 'rag_interpretation',
        'fault_analysis', 'higher_model_reassessment', 'parent_disposition',
        'report_draft', 'report_fidelity'
    )
);

ALTER TABLE public.agent_run_tasks ADD COLUMN IF NOT EXISTS input_schema_version text;
ALTER TABLE public.agent_run_tasks ADD COLUMN IF NOT EXISTS input_hash text;
ALTER TABLE public.agent_run_tasks ADD COLUMN IF NOT EXISTS input_snapshot_origin text;
ALTER TABLE public.agent_run_tasks ADD COLUMN IF NOT EXISTS input_snapshot_status text;
UPDATE public.agent_run_tasks task
SET input_schema_version = run.input_schema_version,
    input_hash = run.input_hash,
    input_snapshot_origin = run.input_snapshot_origin,
    input_snapshot_status = run.input_snapshot_status
FROM public.agent_runs run
WHERE run.run_id = task.run_id;
ALTER TABLE public.agent_run_tasks ALTER COLUMN input_snapshot_origin SET NOT NULL;
ALTER TABLE public.agent_run_tasks ALTER COLUMN input_snapshot_origin SET DEFAULT 'native_v2';
ALTER TABLE public.agent_run_tasks ALTER COLUMN input_snapshot_status SET NOT NULL;
ALTER TABLE public.agent_run_tasks ALTER COLUMN input_snapshot_status SET DEFAULT 'unavailable';
ALTER TABLE public.agent_run_tasks ADD CONSTRAINT agent_run_tasks_input_origin_check
    CHECK (input_snapshot_origin IN ('native_v2', 'legacy_reconstructed_v008', 'legacy_v1'));
ALTER TABLE public.agent_run_tasks ADD CONSTRAINT agent_run_tasks_input_status_check
    CHECK (input_snapshot_status IN ('available', 'unavailable'));

CREATE TABLE public.agent_stage_snapshots (
    stage_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    stage_name text NOT NULL CHECK (stage_name IN (
        'ml_validation', 'weather_context', 'rag_retrieval', 'rag_interpretation',
        'fault_analysis', 'higher_model_reassessment', 'parent_disposition',
        'report_draft', 'report_fidelity'
    )),
    stage_kind text NOT NULL CHECK (stage_kind IN ('quality', 'orchestration')),
    attempt integer NOT NULL DEFAULT 1 CHECK (attempt > 0),
    execution_status text NOT NULL CHECK (
        execution_status IN ('passed', 'failed', 'unavailable', 'skipped', 'reused')
    ),
    quality_status text CHECK (
        quality_status IS NULL OR quality_status IN (
            'passed', 'partial', 'retry', 'insufficient', 'unavailable', 'skipped'
        )
    ),
    score double precision CHECK (score IS NULL OR (score >= 0 AND score <= 100)),
    stage_input_hash text NOT NULL CHECK (stage_input_hash ~ '^[0-9a-f]{64}$'),
    output_snapshot jsonb NOT NULL CHECK (jsonb_typeof(output_snapshot) = 'object'),
    output_hash text NOT NULL CHECK (output_hash ~ '^[0-9a-f]{64}$'),
    contract_version text NOT NULL,
    component_versions jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(component_versions) = 'object'),
    reused_from_snapshot_id uuid REFERENCES public.agent_stage_snapshots(stage_snapshot_id)
        ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT agent_stage_snapshots_run_stage_attempt_key UNIQUE (run_id, stage_name, attempt),
    CONSTRAINT agent_stage_snapshots_no_self_reuse CHECK (
        reused_from_snapshot_id IS NULL OR reused_from_snapshot_id <> stage_snapshot_id
    ),
    CONSTRAINT agent_stage_snapshots_score_contract CHECK (
        (stage_kind = 'orchestration' AND quality_status IS NULL AND score IS NULL)
        OR (stage_kind = 'quality' AND quality_status IN ('passed', 'partial', 'retry', 'insufficient')
            AND score IS NOT NULL)
        OR (stage_kind = 'quality' AND quality_status IN ('unavailable', 'skipped')
            AND score IS NULL)
    )
);
CREATE INDEX agent_stage_snapshots_run_idx
    ON public.agent_stage_snapshots(run_id, stage_name, attempt DESC);

CREATE TABLE public.agent_rerun_requests (
    rerun_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_review_id uuid NOT NULL UNIQUE
        REFERENCES public.agent_run_reviews(review_id) ON DELETE RESTRICT,
    source_run_id uuid NOT NULL REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    child_run_id uuid UNIQUE REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    target_stage text NOT NULL CHECK (target_stage IN (
        'ml_validation', 'weather_context', 'rag_retrieval', 'rag_interpretation',
        'fault_analysis', 'higher_model_reassessment', 'parent_disposition',
        'report_draft', 'report_fidelity'
    )),
    status text NOT NULL CHECK (status IN (
        'queued', 'scheduled', 'schedule_failed', 'blocked_integration_disabled',
        'blocked_legacy_input_unavailable', 'policy_candidate_created', 'rerun_limit_reached'
    )),
    idempotency_key text NOT NULL UNIQUE,
    request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX agent_rerun_requests_status_idx
    ON public.agent_rerun_requests(status, created_at);

CREATE UNIQUE INDEX agent_run_tasks_one_graph_per_run_uidx
ON public.agent_run_tasks (run_id)
WHERE task_key IN ('agent_graph:v1', 'agent_graph:v2');

DO $artifact_preflight$
BEGIN
    IF EXISTS (
        SELECT run_id, name, count(*)
        FROM public.agent_run_artifacts
        GROUP BY run_id, name
        HAVING count(*) > 1
    ) THEN
        RAISE EXCEPTION 'v008 preflight failed: duplicate legacy agent artifacts';
    END IF;
END
$artifact_preflight$;

DROP INDEX IF EXISTS public.agent_run_artifact_run_name_idx;
ALTER TABLE public.agent_run_artifacts ADD COLUMN IF NOT EXISTS source_output_hash text;
ALTER TABLE public.agent_run_artifacts ADD COLUMN IF NOT EXISTS source_review_id uuid;
ALTER TABLE public.agent_run_artifacts ADD COLUMN IF NOT EXISTS contract_version text;
UPDATE public.agent_run_artifacts
SET contract_version = 'artifact.legacy-v1'
WHERE contract_version IS NULL;
ALTER TABLE public.agent_run_artifacts ALTER COLUMN contract_version SET NOT NULL;
ALTER TABLE public.agent_run_artifacts ALTER COLUMN contract_version
    SET DEFAULT 'artifact.output-v2';
ALTER TABLE public.agent_run_artifacts ADD CONSTRAINT agent_run_artifacts_source_review_id_fkey
    FOREIGN KEY (source_review_id) REFERENCES public.agent_run_reviews(review_id) ON DELETE RESTRICT;
ALTER TABLE public.agent_run_artifacts ADD CONSTRAINT agent_run_artifacts_output_contract_check CHECK (
    (contract_version = 'artifact.legacy-v1' AND source_output_hash IS NULL)
    OR (contract_version <> 'artifact.legacy-v1' AND source_output_hash ~ '^[0-9a-f]{64}$')
);
CREATE UNIQUE INDEX agent_run_artifacts_output_lineage_uidx
    ON public.agent_run_artifacts(run_id, name, source_output_hash) NULLS NOT DISTINCT;
