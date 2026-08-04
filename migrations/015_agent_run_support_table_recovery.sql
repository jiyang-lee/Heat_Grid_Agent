COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 015';

CREATE SEQUENCE IF NOT EXISTS public.agent_run_events_event_id_seq;

CREATE TABLE IF NOT EXISTS public.agent_run_events (
    event_id bigint PRIMARY KEY
        DEFAULT nextval('public.agent_run_events_event_id_seq'::regclass),
    run_id uuid NOT NULL
        REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    event_type text NOT NULL,
    message text NOT NULL,
    payload jsonb,
    operation_key text,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER SEQUENCE public.agent_run_events_event_id_seq
    OWNED BY public.agent_run_events.event_id;

CREATE INDEX IF NOT EXISTS agent_run_events_run_idx
    ON public.agent_run_events(run_id, event_id);
CREATE UNIQUE INDEX IF NOT EXISTS agent_run_events_operation_key_uidx
    ON public.agent_run_events(operation_key) WHERE operation_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS agent_run_events_v3_snapshot_idx
    ON public.agent_run_events(run_id, event_type, event_id DESC);

CREATE TABLE IF NOT EXISTS public.agent_run_artifacts (
    artifact_id uuid PRIMARY KEY,
    run_id uuid NOT NULL
        REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    kind text NOT NULL,
    name text NOT NULL,
    uri text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    source_output_hash text,
    source_review_id uuid
        REFERENCES public.agent_run_reviews(review_id) ON DELETE RESTRICT,
    contract_version text NOT NULL DEFAULT 'artifact.output-v2',
    CONSTRAINT agent_run_artifacts_output_contract_check CHECK (
        (contract_version = 'artifact.legacy-v1' AND source_output_hash IS NULL)
        OR (
            contract_version <> 'artifact.legacy-v1'
            AND source_output_hash ~ '^[0-9a-f]{64}$'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS agent_run_artifacts_output_lineage_uidx
    ON public.agent_run_artifacts(run_id, name, source_output_hash)
    NULLS NOT DISTINCT;

CREATE TABLE IF NOT EXISTS public.agent_run_actions (
    run_id uuid NOT NULL
        REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    action_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    requested_by text,
    artifact_id uuid
        REFERENCES public.agent_run_artifacts(artifact_id) ON DELETE SET NULL,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, action_name)
);
