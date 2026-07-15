CREATE TABLE IF NOT EXISTS priority_evaluation_runs (
    evaluation_run_id uuid PRIMARY KEY,
    as_of_time timestamptz NOT NULL,
    stale_after_seconds integer NOT NULL CHECK (stale_after_seconds > 0),
    model_version text NOT NULL,
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    is_active boolean NOT NULL DEFAULT false,
    target_count integer NOT NULL DEFAULT 0,
    success_count integer NOT NULL DEFAULT 0,
    stale_count integer NOT NULL DEFAULT 0,
    missing_count integer NOT NULL DEFAULT 0,
    ranked_count integer NOT NULL DEFAULT 0,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);

CREATE TABLE IF NOT EXISTS priority_evaluation_results (
    evaluation_result_id uuid PRIMARY KEY,
    evaluation_run_id uuid NOT NULL
        REFERENCES priority_evaluation_runs(evaluation_run_id) ON DELETE CASCADE,
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    substation_uid uuid NOT NULL,
    source_window_id uuid,
    source_window_start timestamptz,
    source_window_end timestamptz,
    source_card_id uuid,
    source_priority_decision_id uuid,
    priority_score double precision,
    priority_rank integer,
    rank_included boolean NOT NULL DEFAULT false,
    priority_level text,
    risk_score double precision,
    anomaly_score double precision,
    anomaly_label boolean,
    leadtime_bucket text,
    leadtime_urgency_score double precision,
    leadtime_hours double precision,
    freshness_status text NOT NULL
        CHECK (freshness_status IN ('fresh', 'stale', 'missing')),
    data_age_seconds double precision,
    model_components jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (evaluation_run_id, manufacturer_id, substation_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS priority_evaluation_one_active_idx
ON priority_evaluation_runs(is_active) WHERE is_active;

CREATE INDEX IF NOT EXISTS priority_evaluation_completed_idx
ON priority_evaluation_runs(status, as_of_time DESC, completed_at DESC);

CREATE INDEX IF NOT EXISTS priority_evaluation_result_rank_idx
ON priority_evaluation_results(evaluation_run_id, rank_included, priority_rank);

CREATE INDEX IF NOT EXISTS priority_evaluation_result_substation_idx
ON priority_evaluation_results(manufacturer_id, substation_id, evaluation_run_id);

DO $$
BEGIN
    IF to_regclass('public.ops_alert_queue') IS NOT NULL THEN
        ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS evaluation_run_id uuid;
        ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS manufacturer_id text;
        ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS substation_id integer;
        ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS substation_uid uuid;
        UPDATE ops_alert_queue alert
        SET substation_uid = substation.substation_uid
        FROM substations substation
        WHERE alert.substation_uid IS NULL
          AND alert.manufacturer_id = substation.manufacturer_id
          AND alert.substation_id = substation.substation_id;
        ALTER TABLE ops_alert_queue ALTER COLUMN substation_uid SET NOT NULL;
        ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS priority_rank integer;
        ALTER TABLE ops_alert_queue ADD COLUMN IF NOT EXISTS freshness_status text;
        ALTER TABLE ops_alert_queue DROP CONSTRAINT IF EXISTS ops_alert_queue_card_id_key;
        CREATE UNIQUE INDEX IF NOT EXISTS ops_alert_queue_evaluation_substation_uidx
        ON ops_alert_queue(evaluation_run_id, manufacturer_id, substation_id)
        WHERE evaluation_run_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS ops_alert_queue_evaluation_idx
        ON ops_alert_queue(evaluation_run_id, status, priority_score DESC);
    END IF;

    IF to_regclass('public.agent_runs') IS NOT NULL THEN
        ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS evaluation_run_id uuid;
        ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS manufacturer_id text;
        ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS substation_id integer;
    END IF;
END
$$;
