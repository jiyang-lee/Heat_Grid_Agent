COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 011';

ALTER TABLE public.priority_evaluation_runs
    ADD COLUMN stream_key text NOT NULL DEFAULT 'default';
ALTER TABLE public.priority_evaluation_runs
    ADD COLUMN source_kind text NOT NULL DEFAULT 'batch'
        CHECK (source_kind IN ('batch', 'replay', 'live', 'manual'));
ALTER TABLE public.priority_evaluation_runs
    ADD COLUMN source_run_id uuid;
ALTER TABLE public.priority_evaluation_runs
    ADD COLUMN source_dataset_version text;
DROP INDEX IF EXISTS public.priority_evaluation_one_active_idx;
CREATE UNIQUE INDEX priority_evaluation_one_active_per_stream_idx
    ON public.priority_evaluation_runs(stream_key) WHERE is_active;
CREATE INDEX priority_evaluation_stream_completed_idx
    ON public.priority_evaluation_runs(stream_key, status, as_of_time DESC, completed_at DESC);

ALTER TABLE public.ops_alert_queue
    ADD COLUMN stream_key text NOT NULL DEFAULT 'default';
ALTER TABLE public.ops_alert_queue
    ADD COLUMN synthetic boolean NOT NULL DEFAULT false;
ALTER TABLE public.ops_alert_queue
    ADD COLUMN replay_run_id uuid;
CREATE INDEX ops_alert_queue_stream_status_idx
    ON public.ops_alert_queue(stream_key, status, priority_score DESC);

CREATE TABLE public.replay_datasets (
    dataset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_version text NOT NULL UNIQUE,
    package_sha256 text NOT NULL UNIQUE CHECK (package_sha256 ~ '^[0-9a-f]{64}$'),
    package_uri text NOT NULL,
    extracted_root text NOT NULL,
    manifest jsonb NOT NULL CHECK (jsonb_typeof(manifest) = 'object'),
    status text NOT NULL CHECK (status IN (
        'importing', 'validating', 'available', 'invalid', 'disabled', 'archived'
    )),
    expected_substations integer NOT NULL CHECK (expected_substations > 0),
    source_interval_seconds integer NOT NULL CHECK (source_interval_seconds > 0),
    window_ticks integer NOT NULL CHECK (window_ticks > 0),
    replay_start timestamptz NOT NULL,
    replay_end timestamptz NOT NULL CHECK (replay_end > replay_start),
    current_model_validation jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(current_model_validation) = 'object'),
    imported_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    validated_at timestamptz,
    disabled_at timestamptz
);

CREATE TABLE public.replay_dataset_files (
    dataset_file_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id uuid NOT NULL REFERENCES public.replay_datasets(dataset_id) ON DELETE RESTRICT,
    relative_path text NOT NULL CHECK (relative_path <> '' AND relative_path !~ '(^|/)\\.\\.(/|$)'),
    file_kind text NOT NULL CHECK (file_kind IN (
        'manifest', 'raw_shard', 'window_shard', 'sensor_manifest',
        'scenario_manifest', 'seek_points', 'validation_report', 'index'
    )),
    byte_size bigint NOT NULL CHECK (byte_size >= 0),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    range_start timestamptz,
    range_end timestamptz,
    row_count bigint,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (dataset_id, relative_path)
);

CREATE TABLE public.replay_runs (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id uuid NOT NULL REFERENCES public.replay_datasets(dataset_id) ON DELETE RESTRICT,
    stream_key text NOT NULL UNIQUE,
    state text NOT NULL CHECK (state IN (
        'ready', 'running', 'paused', 'completed', 'error', 'reset', 'superseded', 'cancelled'
    )),
    version integer NOT NULL DEFAULT 1 CHECK (version > 0),
    cursor bigint NOT NULL DEFAULT 0 CHECK (cursor >= 0),
    start_at timestamptz NOT NULL,
    current_simulated_at timestamptz,
    last_emitted_sequence bigint,
    last_scored_window_end timestamptz,
    last_evaluation_run_id uuid REFERENCES public.priority_evaluation_runs(evaluation_run_id) ON DELETE RESTRICT,
    speed_multiplier double precision NOT NULL DEFAULT 1.0 CHECK (speed_multiplier > 0),
    tick_seconds double precision NOT NULL CHECK (tick_seconds > 0),
    lease_owner text,
    lease_expires_at timestamptz,
    heartbeat_at timestamptz,
    error_code text,
    error_detail text,
    requested_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX replay_runs_lease_idx
    ON public.replay_runs(state, lease_expires_at, updated_at DESC);

CREATE TABLE public.replay_run_commands (
    command_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES public.replay_runs(run_id) ON DELETE RESTRICT,
    command_type text NOT NULL CHECK (command_type IN (
        'start', 'pause', 'resume', 'reset', 'seek', 'set_speed', 'cancel'
    )),
    expected_run_version integer NOT NULL CHECK (expected_run_version > 0),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    status text NOT NULL CHECK (status IN ('queued', 'claimed', 'applied', 'rejected', 'failed')),
    idempotency_key text NOT NULL UNIQUE,
    requested_by text NOT NULL,
    claimed_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    applied_at timestamptz,
    error text
);
CREATE INDEX replay_run_commands_claim_idx
    ON public.replay_run_commands(status, created_at);

CREATE TABLE public.replay_tick_batches (
    tick_batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES public.replay_runs(run_id) ON DELETE RESTRICT,
    sequence bigint NOT NULL CHECK (sequence >= 0),
    phase text NOT NULL CHECK (phase IN ('warmup', 'replay')),
    simulated_at timestamptz NOT NULL,
    emitted_at timestamptz NOT NULL DEFAULT now(),
    readings jsonb NOT NULL CHECK (jsonb_typeof(readings) = 'array'),
    quality_summary jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(quality_summary) = 'object'),
    scenario_ids jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(scenario_ids) = 'array'),
    payload_hash text NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, sequence)
);

CREATE TABLE public.replay_latest_readings (
    run_id uuid NOT NULL REFERENCES public.replay_runs(run_id) ON DELETE RESTRICT,
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    sequence bigint NOT NULL CHECK (sequence >= 0),
    simulated_at timestamptz NOT NULL,
    values jsonb NOT NULL CHECK (jsonb_typeof(values) = 'object'),
    quality jsonb NOT NULL CHECK (jsonb_typeof(quality) = 'object'),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, manufacturer_id, substation_id)
);

CREATE TABLE public.replay_window_evaluations (
    replay_window_evaluation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES public.replay_runs(run_id) ON DELETE RESTRICT,
    window_start timestamptz NOT NULL,
    window_end timestamptz NOT NULL CHECK (window_end > window_start),
    evaluation_run_id uuid NOT NULL REFERENCES public.priority_evaluation_runs(evaluation_run_id) ON DELETE RESTRICT,
    model_version text NOT NULL,
    input_hash text NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
    result_hash text NOT NULL CHECK (result_hash ~ '^[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    inference_duration_ms integer CHECK (inference_duration_ms >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (run_id, window_end)
);

CREATE TABLE public.replay_stream_events (
    event_id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES public.replay_runs(run_id) ON DELETE RESTRICT,
    event_type text NOT NULL,
    sequence bigint,
    simulated_at timestamptz,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    operation_key text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX replay_stream_events_operation_uidx
    ON public.replay_stream_events(operation_key) WHERE operation_key IS NOT NULL;
CREATE INDEX replay_stream_events_run_event_idx
    ON public.replay_stream_events(run_id, event_id);

GRANT SELECT, INSERT, UPDATE ON public.replay_datasets, public.replay_dataset_files,
    public.replay_runs, public.replay_run_commands, public.replay_tick_batches,
    public.replay_latest_readings, public.replay_window_evaluations,
    public.replay_stream_events TO heatgrid_app;
GRANT USAGE, SELECT ON SEQUENCE public.replay_stream_events_event_id_seq TO heatgrid_app;
