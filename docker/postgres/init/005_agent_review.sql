CREATE TABLE IF NOT EXISTS agent_run_review_snapshots (
    run_id uuid NOT NULL,
    schema_version text NOT NULL DEFAULT 'agent_run_review.v1'
        CHECK (schema_version = 'agent_run_review.v1'),
    snapshot_hash text NOT NULL
        CHECK (snapshot_hash ~ '^[0-9a-f]{64}$'),
    snapshot jsonb NOT NULL
        CHECK (jsonb_typeof(snapshot) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id)
);

CREATE INDEX IF NOT EXISTS agent_run_review_snapshots_created_idx
ON agent_run_review_snapshots(created_at DESC, run_id DESC);

CREATE TABLE IF NOT EXISTS agent_run_reviews (
    review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL,
    review_version integer NOT NULL CHECK (review_version > 0),
    idempotency_key text NOT NULL
        CHECK (char_length(idempotency_key) BETWEEN 1 AND 200),
    request_hash text NOT NULL
        CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    decision text NOT NULL
        CHECK (decision IN ('approve', 'correct', 'keep_human_review')),
    reviewer text NOT NULL
        CHECK (char_length(btrim(reviewer)) BETWEEN 1 AND 120),
    reason text NOT NULL
        CHECK (char_length(btrim(reason)) BETWEEN 1 AND 2000),
    disposition text,
    correction jsonb,
    evidence_annotations jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(evidence_annotations) = 'array'),
    operator_labels jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(operator_labels) = 'array'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, review_version),
    UNIQUE (run_id, idempotency_key),
    CHECK (correction IS NULL OR jsonb_typeof(correction) = 'object')
);

CREATE INDEX IF NOT EXISTS agent_run_reviews_run_created_idx
ON agent_run_reviews(run_id, created_at DESC, review_version DESC);

CREATE TABLE IF NOT EXISTS agent_policy_candidates (
    candidate_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_review_id uuid NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    scope text NOT NULL
        CHECK (scope IN (
            'evidence_threshold',
            'diagnostic_trigger',
            'human_review_route'
        )),
    proposal jsonb NOT NULL
        CHECK (jsonb_typeof(proposal) = 'object'),
    supporting_evidence jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(supporting_evidence) = 'array'),
    decision_history jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(decision_history) = 'array'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_policy_candidates_status_created_idx
ON agent_policy_candidates(status, created_at DESC, candidate_id DESC);

DO $agent_review$
BEGIN
    IF to_regclass('public.agent_runs') IS NOT NULL THEN
        ALTER TABLE agent_runs
        ADD COLUMN IF NOT EXISTS review_snapshot_expected boolean;
        ALTER TABLE agent_runs
        ALTER COLUMN review_snapshot_expected SET DEFAULT true;
    END IF;

    IF to_regclass('public.agent_runs') IS NOT NULL
       AND to_regclass('public.agent_run_review_snapshots') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'agent_run_review_snapshots_run_id_fkey'
             AND conrelid = 'agent_run_review_snapshots'::regclass
       ) THEN
        ALTER TABLE agent_run_review_snapshots
        ADD CONSTRAINT agent_run_review_snapshots_run_id_fkey
        FOREIGN KEY (run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE;
    END IF;

    IF to_regclass('public.agent_runs') IS NOT NULL
       AND to_regclass('public.agent_run_reviews') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'agent_run_reviews_run_id_fkey'
             AND conrelid = 'agent_run_reviews'::regclass
       ) THEN
        ALTER TABLE agent_run_reviews
        ADD CONSTRAINT agent_run_reviews_run_id_fkey
        FOREIGN KEY (run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE;
    END IF;

    IF to_regclass('public.agent_run_reviews') IS NOT NULL
       AND to_regclass('public.agent_policy_candidates') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'agent_policy_candidates_source_review_id_fkey'
             AND conrelid = 'agent_policy_candidates'::regclass
       ) THEN
        ALTER TABLE agent_policy_candidates
        ADD CONSTRAINT agent_policy_candidates_source_review_id_fkey
        FOREIGN KEY (source_review_id)
        REFERENCES agent_run_reviews(review_id) ON DELETE CASCADE;
    END IF;
END
$agent_review$;

DO $agent_review_list_indexes$
BEGIN
    IF to_regclass('public.agent_runs') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS agent_runs_v3_list_idx
        ON agent_runs(created_at DESC, run_id DESC);
    END IF;

    IF to_regclass('public.agent_run_tasks') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS agent_run_tasks_v3_worker_idx
        ON agent_run_tasks(run_id, task_key, status);
    END IF;

    IF to_regclass('public.agent_run_events') IS NOT NULL THEN
        CREATE INDEX IF NOT EXISTS agent_run_events_v3_snapshot_idx
        ON agent_run_events(run_id, event_type, event_id DESC);
    END IF;
END
$agent_review_list_indexes$;
