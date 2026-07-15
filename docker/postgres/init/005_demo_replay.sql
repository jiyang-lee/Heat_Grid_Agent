CREATE TABLE IF NOT EXISTS demo_replay_runs (
    run_id uuid PRIMARY KEY,
    dataset_version text NOT NULL,
    state text NOT NULL CHECK (
        state IN ('running', 'paused', 'completed', 'error', 'reset', 'superseded')
    ),
    cursor bigint NOT NULL DEFAULT 0 CHECK (cursor >= 0),
    start_at timestamptz NOT NULL,
    replay_start timestamptz NOT NULL,
    replay_end timestamptz NOT NULL,
    current_simulated_at timestamptz,
    has_scored_window boolean NOT NULL DEFAULT false,
    last_evaluation_run_id uuid,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS sensor_readings (
    reading_id bigserial PRIMARY KEY,
    run_id uuid NOT NULL REFERENCES demo_replay_runs(run_id) ON DELETE CASCADE,
    dataset_version text NOT NULL,
    sequence bigint NOT NULL,
    phase text NOT NULL CHECK (phase IN ('warmup', 'replay')),
    simulated_at timestamptz NOT NULL,
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    values jsonb NOT NULL,
    quality jsonb NOT NULL,
    is_synthetic boolean NOT NULL DEFAULT true,
    scenario_id text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, sequence, manufacturer_id, substation_id)
);

CREATE INDEX IF NOT EXISTS demo_replay_runs_state_idx
ON demo_replay_runs(state, updated_at DESC);

CREATE INDEX IF NOT EXISTS sensor_readings_time_idx
ON sensor_readings(run_id, simulated_at, substation_id);

CREATE INDEX IF NOT EXISTS sensor_readings_substation_idx
ON sensor_readings(substation_id, simulated_at DESC);
