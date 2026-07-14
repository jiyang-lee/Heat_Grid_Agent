CREATE TABLE IF NOT EXISTS public.fault_events (
    fault_event_id text PRIMARY KEY,
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    fault_label text NOT NULL,
    estimated_lead_time_hours double precision,
    lead_time_bucket text
);

CREATE TABLE IF NOT EXISTS public.sensor_readings (
    sensor_reading_id uuid PRIMARY KEY,
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    reading_time timestamptz NOT NULL,
    source_sensor text NOT NULL,
    sensor_value double precision,
    unit text,
    source_file text
);

ALTER TABLE public.substations ADD COLUMN IF NOT EXISTS substation_uid uuid;
UPDATE public.substations
SET substation_uid = gen_random_uuid()
WHERE substation_uid IS NULL;
ALTER TABLE public.substations ALTER COLUMN substation_uid SET NOT NULL;
ALTER TABLE public.substations ALTER COLUMN substation_uid SET DEFAULT gen_random_uuid();

DO $uid_preflight$
DECLARE
    target record;
    missing_count bigint;
BEGIN
    FOR target IN
        SELECT * FROM (VALUES
            ('fault_events'),
            ('sensor_readings'),
            ('windows'),
            ('priority_evaluation_results'),
            ('ops_alert_queue'),
            ('agent_runs')
        ) AS tables(table_name)
    LOOP
        EXECUTE format(
            'SELECT count(*) FROM public.%I child '
            'LEFT JOIN public.substations parent '
            'ON parent.manufacturer_id = child.manufacturer_id '
            'AND parent.substation_id = child.substation_id '
            'WHERE child.manufacturer_id IS NOT NULL '
            'AND child.substation_id IS NOT NULL '
            'AND parent.substation_uid IS NULL',
            target.table_name
        ) INTO missing_count;
        IF missing_count > 0 THEN
            RAISE EXCEPTION 'substation UID mapping missing for %.% rows',
                target.table_name, missing_count;
        END IF;
    END LOOP;

    SELECT count(*) INTO missing_count
    FROM public.substation_building_context context
    LEFT JOIN LATERAL (
        SELECT count(*) AS matches
        FROM public.substations substation
        WHERE substation.substation_id = context.substation_id
    ) mapped ON true
    WHERE mapped.matches <> 1;
    IF missing_count > 0 THEN
        RAISE EXCEPTION 'substation_building_context has % ambiguous or missing UID mappings',
            missing_count;
    END IF;
END
$uid_preflight$;

ALTER TABLE public.fault_events ADD COLUMN IF NOT EXISTS substation_uid uuid;
ALTER TABLE public.sensor_readings ADD COLUMN IF NOT EXISTS substation_uid uuid;
ALTER TABLE public.windows ADD COLUMN IF NOT EXISTS substation_uid uuid;
ALTER TABLE public.priority_evaluation_results ADD COLUMN IF NOT EXISTS substation_uid uuid;
ALTER TABLE public.ops_alert_queue ADD COLUMN IF NOT EXISTS substation_uid uuid;
ALTER TABLE public.agent_runs ADD COLUMN IF NOT EXISTS substation_uid uuid;
ALTER TABLE public.substation_building_context ADD COLUMN IF NOT EXISTS substation_uid uuid;

UPDATE public.fault_events child
SET substation_uid = parent.substation_uid
FROM public.substations parent
WHERE child.substation_uid IS NULL
  AND parent.manufacturer_id = child.manufacturer_id
  AND parent.substation_id = child.substation_id;

UPDATE public.sensor_readings child
SET substation_uid = parent.substation_uid
FROM public.substations parent
WHERE child.substation_uid IS NULL
  AND parent.manufacturer_id = child.manufacturer_id
  AND parent.substation_id = child.substation_id;

UPDATE public.windows child
SET substation_uid = parent.substation_uid
FROM public.substations parent
WHERE child.substation_uid IS NULL
  AND parent.manufacturer_id = child.manufacturer_id
  AND parent.substation_id = child.substation_id;

UPDATE public.priority_evaluation_results child
SET substation_uid = parent.substation_uid
FROM public.substations parent
WHERE child.substation_uid IS NULL
  AND parent.manufacturer_id = child.manufacturer_id
  AND parent.substation_id = child.substation_id;

UPDATE public.ops_alert_queue child
SET substation_uid = parent.substation_uid
FROM public.substations parent
WHERE child.substation_uid IS NULL
  AND parent.manufacturer_id = child.manufacturer_id
  AND parent.substation_id = child.substation_id;

UPDATE public.agent_runs child
SET substation_uid = parent.substation_uid
FROM public.substations parent
WHERE child.substation_uid IS NULL
  AND parent.manufacturer_id = child.manufacturer_id
  AND parent.substation_id = child.substation_id;

UPDATE public.substation_building_context context
SET substation_uid = parent.substation_uid
FROM public.substations parent
WHERE context.substation_uid IS NULL
  AND parent.substation_id = context.substation_id;

ALTER TABLE public.fault_events ALTER COLUMN substation_uid SET NOT NULL;
ALTER TABLE public.sensor_readings ALTER COLUMN substation_uid SET NOT NULL;
ALTER TABLE public.windows ALTER COLUMN substation_uid SET NOT NULL;
ALTER TABLE public.priority_evaluation_results ALTER COLUMN substation_uid SET NOT NULL;
ALTER TABLE public.ops_alert_queue ALTER COLUMN substation_uid SET NOT NULL;
ALTER TABLE public.agent_runs ALTER COLUMN substation_uid SET NOT NULL;
ALTER TABLE public.substation_building_context ALTER COLUMN substation_uid SET NOT NULL;

ALTER TABLE public.fault_events DROP CONSTRAINT IF EXISTS fault_events_manufacturer_id_substation_id_fkey;
ALTER TABLE public.sensor_readings DROP CONSTRAINT IF EXISTS sensor_readings_manufacturer_id_substation_id_fkey;
ALTER TABLE public.windows DROP CONSTRAINT IF EXISTS windows_manufacturer_id_substation_id_fkey;
ALTER TABLE public.ops_alert_queue DROP CONSTRAINT IF EXISTS ops_alert_queue_substation_fkey;
ALTER TABLE public.agent_runs DROP CONSTRAINT IF EXISTS agent_runs_substation_fkey;
ALTER TABLE public.substations DROP CONSTRAINT IF EXISTS substations_pkey;
ALTER TABLE public.substations ADD CONSTRAINT substations_pkey PRIMARY KEY (substation_uid);
ALTER TABLE public.substations DROP CONSTRAINT IF EXISTS substations_natural_key;
ALTER TABLE public.substations
ADD CONSTRAINT substations_natural_key UNIQUE (manufacturer_id, substation_id);

ALTER TABLE public.substation_building_context DROP CONSTRAINT IF EXISTS substation_building_context_pkey;
ALTER TABLE public.substation_building_context
ADD CONSTRAINT substation_building_context_pkey PRIMARY KEY (substation_uid);
ALTER TABLE public.substation_building_context
ADD CONSTRAINT substation_building_context_substation_id_key UNIQUE (substation_id);

DROP INDEX IF EXISTS public.ops_alert_queue_evaluation_substation_uidx;
CREATE UNIQUE INDEX ops_alert_queue_evaluation_substation_uidx
ON public.ops_alert_queue(evaluation_run_id, substation_uid)
WHERE evaluation_run_id IS NOT NULL;

ALTER TABLE public.fault_events
ADD CONSTRAINT fault_events_substation_uid_fkey
FOREIGN KEY (substation_uid) REFERENCES public.substations(substation_uid)
ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.sensor_readings
ADD CONSTRAINT sensor_readings_substation_uid_fkey
FOREIGN KEY (substation_uid) REFERENCES public.substations(substation_uid)
ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.windows
ADD CONSTRAINT windows_substation_uid_fkey
FOREIGN KEY (substation_uid) REFERENCES public.substations(substation_uid)
ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.priority_evaluation_results
ADD CONSTRAINT priority_evaluation_results_substation_uid_fkey
FOREIGN KEY (substation_uid) REFERENCES public.substations(substation_uid)
ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.ops_alert_queue
ADD CONSTRAINT ops_alert_queue_substation_uid_fkey
FOREIGN KEY (substation_uid) REFERENCES public.substations(substation_uid)
ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.agent_runs
ADD CONSTRAINT agent_runs_substation_uid_fkey
FOREIGN KEY (substation_uid) REFERENCES public.substations(substation_uid)
ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.substation_building_context
ADD CONSTRAINT substation_building_context_substation_uid_fkey
FOREIGN KEY (substation_uid) REFERENCES public.substations(substation_uid)
ON DELETE RESTRICT NOT VALID;

ALTER TABLE public.windows DROP CONSTRAINT IF EXISTS windows_fault_event_id_fkey;
ALTER TABLE public.windows
ADD CONSTRAINT windows_fault_event_id_fkey
FOREIGN KEY (fault_event_id) REFERENCES public.fault_events(fault_event_id)
ON DELETE SET NULL NOT VALID;

ALTER TABLE public.human_review_tasks ADD COLUMN IF NOT EXISTS subject_type text;
ALTER TABLE public.human_review_tasks ADD COLUMN IF NOT EXISTS subject_key text;

UPDATE public.human_review_tasks
SET subject_type = CASE
        WHEN run_id IS NOT NULL THEN 'agent_run'
        WHEN candidate_id IS NOT NULL THEN 'evidence_candidate'
        WHEN retrain_job_id IS NOT NULL THEN 'retrain_job'
        WHEN model_candidate_id IS NOT NULL THEN 'model_candidate'
        ELSE 'review_task'
    END,
    subject_key = COALESCE(
        run_id::text,
        candidate_id::text,
        retrain_job_id::text,
        model_candidate_id::text,
        task_id::text
    )
WHERE subject_type IS NULL OR subject_key IS NULL;

ALTER TABLE public.human_review_tasks ALTER COLUMN subject_type SET NOT NULL;
ALTER TABLE public.human_review_tasks ALTER COLUMN subject_key SET NOT NULL;
ALTER TABLE public.human_review_tasks
ADD CONSTRAINT human_review_tasks_subject_check CHECK (
    (subject_type = 'agent_run' AND run_id IS NOT NULL AND subject_key = run_id::text)
    OR (subject_type <> 'agent_run' AND run_id IS NULL)
);

ALTER TABLE public.agent_run_reviews ADD COLUMN IF NOT EXISTS review_task_id uuid;
ALTER TABLE public.agent_run_reviews ADD COLUMN IF NOT EXISTS subject_type text;
ALTER TABLE public.agent_run_reviews ADD COLUMN IF NOT EXISTS subject_key text;
ALTER TABLE public.agent_run_reviews
ADD COLUMN IF NOT EXISTS review_contract_version integer;
ALTER TABLE public.agent_run_reviews ADD COLUMN IF NOT EXISTS reason_category text;

UPDATE public.agent_run_reviews review
SET review_task_id = task.task_id
FROM public.human_review_tasks task
WHERE review.review_task_id IS NULL
  AND review.idempotency_key = 'legacy-task:' || task.task_id::text;

INSERT INTO public.human_review_tasks (
    task_id, task_type, status, risk_level, title, run_id,
    payload, resolution, reviewed_by, reviewed_at, operation_key,
    subject_type, subject_key
)
SELECT
    review.review_id,
    'agent_run_review',
    CASE review.decision
        WHEN 'approve' THEN 'approved'
        WHEN 'correct' THEN 'corrected'
        ELSE 'rejected'
    END,
    'medium',
    'Reconstructed agent run review',
    review.run_id,
    jsonb_build_object(
        'payload_source', 'migration_reconstruction',
        'source_review_id', review.review_id,
        'run_id', review.run_id,
        'review_version', review.review_version,
        'decision', review.decision,
        'reason', review.reason,
        'correction', COALESCE(review.correction, '{}'::jsonb)
    ),
    jsonb_build_object('decision', review.decision),
    review.reviewer,
    review.created_at,
    'migration-review:' || review.review_id::text,
    'agent_run',
    review.run_id::text
FROM public.agent_run_reviews review
WHERE review.review_task_id IS NULL
ON CONFLICT (task_id) DO NOTHING;

UPDATE public.agent_run_reviews review
SET review_task_id = review.review_id
WHERE review.review_task_id IS NULL;

UPDATE public.agent_run_reviews review
SET subject_type = task.subject_type,
    subject_key = task.subject_key,
    review_contract_version = 1
FROM public.human_review_tasks task
WHERE task.task_id = review.review_task_id
  AND (review.subject_type IS NULL
       OR review.subject_key IS NULL
       OR review.review_contract_version IS NULL);

ALTER TABLE public.agent_run_reviews DROP CONSTRAINT IF EXISTS agent_run_reviews_decision_check;

INSERT INTO public.agent_run_reviews (
    review_task_id, run_id, subject_type, subject_key, review_contract_version,
    review_version, idempotency_key, request_hash, decision, reviewer, reason,
    correction, evidence_annotations, operator_labels
)
SELECT
    task.task_id,
    task.run_id,
    task.subject_type,
    task.subject_key,
    1,
    1,
    'migration-feedback:' || feedback.feedback_id::text,
    encode(digest('migration-feedback:' || feedback.feedback_id::text, 'sha256'), 'hex'),
    CASE
        WHEN feedback.decision = 'approve' THEN 'approve'
        WHEN feedback.decision = 'correct' THEN 'correct'
        ELSE 'reject'
    END,
    feedback.reviewer,
    COALESCE(NULLIF(feedback.metadata ->> 'reason', ''), 'migration reconstruction'),
    NULLIF(feedback.corrected_output, '{}'::jsonb),
    '[]'::jsonb,
    '["migration_reconstruction"]'::jsonb
FROM public.training_feedback feedback
JOIN public.human_review_tasks task ON task.task_id = feedback.task_id
LEFT JOIN public.agent_run_reviews review ON review.review_task_id = task.task_id
WHERE review.review_id IS NULL;

ALTER TABLE public.agent_run_reviews ALTER COLUMN run_id DROP NOT NULL;
ALTER TABLE public.agent_run_reviews ALTER COLUMN review_task_id SET NOT NULL;
ALTER TABLE public.agent_run_reviews ALTER COLUMN subject_type SET NOT NULL;
ALTER TABLE public.agent_run_reviews ALTER COLUMN subject_key SET NOT NULL;
ALTER TABLE public.agent_run_reviews ALTER COLUMN review_contract_version SET NOT NULL;
ALTER TABLE public.agent_run_reviews ALTER COLUMN review_contract_version SET DEFAULT 2;

ALTER TABLE public.agent_run_reviews
ADD CONSTRAINT agent_run_reviews_decision_check
CHECK (decision IN ('approve', 'correct', 'reject', 'keep_human_review'));
ALTER TABLE public.agent_run_reviews
ADD CONSTRAINT agent_run_reviews_subject_check CHECK (
    (subject_type = 'agent_run' AND run_id IS NOT NULL AND subject_key = run_id::text)
    OR (subject_type <> 'agent_run' AND run_id IS NULL)
);
ALTER TABLE public.agent_run_reviews
ADD CONSTRAINT agent_run_reviews_contract_check CHECK (
    review_contract_version = 1
    OR (review_contract_version = 2 AND (
        decision NOT IN ('reject', 'keep_human_review') OR reason_category IS NOT NULL
    ))
);

ALTER TABLE public.agent_run_reviews DROP CONSTRAINT IF EXISTS agent_run_reviews_run_id_review_version_key;
ALTER TABLE public.agent_run_reviews DROP CONSTRAINT IF EXISTS agent_run_reviews_run_id_idempotency_key_key;
CREATE UNIQUE INDEX agent_run_reviews_task_uidx
ON public.agent_run_reviews(review_task_id);
CREATE UNIQUE INDEX agent_run_reviews_idempotency_uidx
ON public.agent_run_reviews(idempotency_key);
CREATE UNIQUE INDEX agent_run_reviews_run_version_uidx
ON public.agent_run_reviews(run_id, review_version) WHERE run_id IS NOT NULL;

ALTER TABLE public.training_feedback ADD COLUMN IF NOT EXISTS source_review_id uuid;
UPDATE public.training_feedback feedback
SET source_review_id = review.review_id
FROM public.agent_run_reviews review
WHERE review.review_task_id = feedback.task_id
  AND feedback.source_review_id IS NULL;
ALTER TABLE public.training_feedback ALTER COLUMN source_review_id SET NOT NULL;
ALTER TABLE public.training_feedback
ADD CONSTRAINT training_feedback_source_review_id_key UNIQUE (source_review_id);

ALTER TABLE public.agent_runs DROP COLUMN IF EXISTS approved_action_task_id;

ALTER TABLE public.agent_runs DROP CONSTRAINT IF EXISTS agent_runs_alert_id_fkey;
ALTER TABLE public.agent_runs ADD CONSTRAINT agent_runs_alert_id_fkey
FOREIGN KEY (alert_id) REFERENCES public.ops_alert_queue(alert_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.agent_runs DROP CONSTRAINT IF EXISTS agent_runs_card_id_fkey;
ALTER TABLE public.agent_runs ADD CONSTRAINT agent_runs_card_id_fkey
FOREIGN KEY (card_id) REFERENCES public.priority_cards(card_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.ops_alert_queue DROP CONSTRAINT IF EXISTS ops_alert_queue_card_id_fkey;
ALTER TABLE public.ops_alert_queue ADD CONSTRAINT ops_alert_queue_card_id_fkey
FOREIGN KEY (card_id) REFERENCES public.priority_cards(card_id) ON DELETE RESTRICT NOT VALID;

ALTER TABLE public.agent_run_events DROP CONSTRAINT IF EXISTS agent_run_events_run_id_fkey;
ALTER TABLE public.agent_run_events ADD CONSTRAINT agent_run_events_run_id_fkey
FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.agent_run_artifacts DROP CONSTRAINT IF EXISTS agent_run_artifacts_run_id_fkey;
ALTER TABLE public.agent_run_artifacts ADD CONSTRAINT agent_run_artifacts_run_id_fkey
FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.agent_run_actions DROP CONSTRAINT IF EXISTS agent_run_actions_run_id_fkey;
ALTER TABLE public.agent_run_actions ADD CONSTRAINT agent_run_actions_run_id_fkey
FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.agent_run_tasks DROP CONSTRAINT IF EXISTS agent_run_tasks_run_id_fkey;
ALTER TABLE public.agent_run_tasks ADD CONSTRAINT agent_run_tasks_run_id_fkey
FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.agent_budget_ledger DROP CONSTRAINT IF EXISTS agent_budget_ledger_run_id_fkey;
ALTER TABLE public.agent_budget_ledger ADD CONSTRAINT agent_budget_ledger_run_id_fkey
FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT NOT VALID;

ALTER TABLE public.human_review_tasks
ADD CONSTRAINT human_review_tasks_run_id_fkey
FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.human_review_tasks
ADD CONSTRAINT human_review_tasks_retrain_job_id_fkey
FOREIGN KEY (retrain_job_id) REFERENCES public.retrain_jobs(job_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.human_review_tasks
ADD CONSTRAINT human_review_tasks_model_candidate_id_fkey
FOREIGN KEY (model_candidate_id) REFERENCES public.model_candidates(candidate_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.agent_runs
ADD CONSTRAINT agent_runs_review_task_id_fkey
FOREIGN KEY (review_task_id) REFERENCES public.human_review_tasks(task_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.agent_run_reviews
ADD CONSTRAINT agent_run_reviews_review_task_id_fkey
FOREIGN KEY (review_task_id) REFERENCES public.human_review_tasks(task_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.evidence_candidates
ADD CONSTRAINT evidence_candidates_run_id_fkey
FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.evidence_candidates
ADD CONSTRAINT evidence_candidates_rag_document_id_fkey
FOREIGN KEY (rag_document_id) REFERENCES public.rag_documents(document_id) ON DELETE SET NULL NOT VALID;
ALTER TABLE public.evidence_candidates
ADD CONSTRAINT evidence_candidates_rag_chunk_id_fkey
FOREIGN KEY (rag_chunk_id) REFERENCES public.rag_chunks(chunk_id) ON DELETE SET NULL NOT VALID;
ALTER TABLE public.training_feedback
ADD CONSTRAINT training_feedback_source_review_id_fkey
FOREIGN KEY (source_review_id) REFERENCES public.agent_run_reviews(review_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.training_feedback DROP CONSTRAINT IF EXISTS training_feedback_task_id_fkey;
ALTER TABLE public.training_feedback ADD CONSTRAINT training_feedback_task_id_fkey
FOREIGN KEY (task_id) REFERENCES public.human_review_tasks(task_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.training_feedback
ADD CONSTRAINT training_feedback_run_id_fkey
FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.training_feedback
ADD CONSTRAINT training_feedback_card_id_fkey
FOREIGN KEY (card_id) REFERENCES public.priority_cards(card_id) ON DELETE RESTRICT NOT VALID;
ALTER TABLE public.retrain_jobs
ADD CONSTRAINT retrain_jobs_model_candidate_id_fkey
FOREIGN KEY (model_candidate_id) REFERENCES public.model_candidates(candidate_id) ON DELETE SET NULL NOT VALID;

DO $validate_v007$
DECLARE
    target record;
BEGIN
    FOR target IN
        SELECT namespace.nspname AS schema_name, relation.relname AS table_name,
               constraint_row.conname
        FROM pg_constraint constraint_row
        JOIN pg_class relation ON relation.oid = constraint_row.conrelid
        JOIN pg_namespace namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname = 'public'
          AND constraint_row.contype = 'f'
          AND NOT constraint_row.convalidated
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I VALIDATE CONSTRAINT %I',
            target.schema_name,
            target.table_name,
            target.conname
        );
    END LOOP;
END
$validate_v007$;

DROP TABLE IF EXISTS public.feature_meta_map;
DROP TABLE IF EXISTS public.window_features;
DROP TABLE IF EXISTS public.llm_ops_notes;
DROP TABLE IF EXISTS public.ops_retrieval_hits;
DROP TABLE IF EXISTS public.ops_tool_calls;
DROP TABLE IF EXISTS public.ops_agent_runs;
