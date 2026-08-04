COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 016';

ALTER TABLE public.ops_alert_queue ADD COLUMN IF NOT EXISTS episode_id uuid;
ALTER TABLE public.ops_alert_queue ADD COLUMN IF NOT EXISTS read_at timestamptz;
ALTER TABLE public.ops_alert_queue ADD COLUMN IF NOT EXISTS read_by text;

CREATE TABLE IF NOT EXISTS public.anomaly_episodes (
    episode_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_key text NOT NULL DEFAULT 'default',
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    lifecycle_status text NOT NULL CHECK (lifecycle_status IN ('pending', 'open', 'resolved')),
    severity text CHECK (severity IS NULL OR severity IN ('normal', 'high', 'critical')),
    alert_id uuid UNIQUE,
    consecutive_anomaly_count integer NOT NULL DEFAULT 0 CHECK (consecutive_anomaly_count >= 0),
    consecutive_normal_count integer NOT NULL DEFAULT 0 CHECK (consecutive_normal_count >= 0),
    last_evaluation_run_id uuid
        REFERENCES public.priority_evaluation_runs(evaluation_run_id) ON DELETE RESTRICT,
    opened_at timestamptz,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (lifecycle_status <> 'open' OR (alert_id IS NOT NULL AND opened_at IS NOT NULL)),
    CHECK (lifecycle_status <> 'resolved' OR resolved_at IS NOT NULL),
    FOREIGN KEY (manufacturer_id, substation_id)
        REFERENCES public.substations(manufacturer_id, substation_id) ON DELETE RESTRICT
);
CREATE UNIQUE INDEX IF NOT EXISTS anomaly_episodes_one_active_per_asset_uidx
    ON public.anomaly_episodes(stream_key, manufacturer_id, substation_id)
    WHERE lifecycle_status IN ('pending', 'open');
CREATE INDEX IF NOT EXISTS anomaly_episodes_status_idx
    ON public.anomaly_episodes(stream_key, lifecycle_status, updated_at DESC);

CREATE TABLE IF NOT EXISTS public.anomaly_episode_consumptions (
    evaluation_run_id uuid PRIMARY KEY
        REFERENCES public.priority_evaluation_runs(evaluation_run_id) ON DELETE RESTRICT,
    stream_key text NOT NULL,
    consumed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.anomaly_episode_events (
    event_id bigserial PRIMARY KEY,
    episode_id uuid
        REFERENCES public.anomaly_episodes(episode_id) ON DELETE RESTRICT,
    evaluation_run_id uuid
        REFERENCES public.priority_evaluation_runs(evaluation_run_id) ON DELETE RESTRICT,
    stream_key text NOT NULL,
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    event_type text NOT NULL CHECK (
        event_type IN ('opened', 'resolved', 'escalated', 'frozen')
    ),
    severity text CHECK (severity IS NULL OR severity IN ('high', 'critical')),
    payload jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (manufacturer_id, substation_id)
        REFERENCES public.substations(manufacturer_id, substation_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS anomaly_episode_events_stream_idx
    ON public.anomaly_episode_events(stream_key, created_at DESC);

DO $operations_alert_episode_fk$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ops_alert_queue_episode_id_fkey'
          AND conrelid = 'public.ops_alert_queue'::regclass
    ) THEN
        ALTER TABLE public.ops_alert_queue
            ADD CONSTRAINT ops_alert_queue_episode_id_fkey
            FOREIGN KEY (episode_id) REFERENCES public.anomaly_episodes(episode_id)
            ON DELETE RESTRICT NOT VALID;
    END IF;
END
$operations_alert_episode_fk$;
CREATE UNIQUE INDEX IF NOT EXISTS ops_alert_queue_episode_uidx
    ON public.ops_alert_queue(episode_id) WHERE episode_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.preventive_projections (
    preventive_projection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    stream_key text NOT NULL DEFAULT 'default',
    manufacturer_id text NOT NULL,
    substation_id integer NOT NULL,
    evaluation_run_id uuid NOT NULL
        REFERENCES public.priority_evaluation_runs(evaluation_run_id) ON DELETE RESTRICT,
    priority_level text NOT NULL CHECK (priority_level IN ('urgent', 'high')),
    priority_score double precision,
    freshness_status text NOT NULL CHECK (freshness_status = 'fresh'),
    reason jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(reason) = 'object'),
    projected_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,
    UNIQUE (stream_key, manufacturer_id, substation_id, evaluation_run_id),
    FOREIGN KEY (manufacturer_id, substation_id)
        REFERENCES public.substations(manufacturer_id, substation_id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS preventive_projections_current_idx
    ON public.preventive_projections(stream_key, projected_at DESC);

CREATE TABLE IF NOT EXISTS public.operations_policy (
    policy_key text PRIMARY KEY CHECK (policy_key = 'default'),
    version integer NOT NULL CHECK (version > 0),
    timezone text NOT NULL CHECK (timezone = 'Asia/Seoul'),
    freshness_threshold_minutes integer NOT NULL CHECK (freshness_threshold_minutes > 0),
    anomaly_confirmations integer NOT NULL CHECK (anomaly_confirmations > 0),
    recovery_confirmations integer NOT NULL CHECK (recovery_confirmations > 0),
    live_source_interval_seconds integer NOT NULL DEFAULT 600 CHECK (live_source_interval_seconds > 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by text NOT NULL
);
INSERT INTO public.operations_policy (
    policy_key,
    version,
    timezone,
    freshness_threshold_minutes,
    anomaly_confirmations,
    recovery_confirmations,
    live_source_interval_seconds,
    updated_by
) VALUES ('default', 1, 'Asia/Seoul', 30, 2, 3, 600, 'operator')
ON CONFLICT (policy_key) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.operations_shift_schedule (
    policy_key text NOT NULL
        REFERENCES public.operations_policy(policy_key) ON DELETE RESTRICT,
    shift_id text NOT NULL,
    label text NOT NULL CHECK (char_length(btrim(label)) BETWEEN 1 AND 80),
    start_time time NOT NULL,
    end_time time NOT NULL,
    position integer NOT NULL CHECK (position IN (1, 2)),
    PRIMARY KEY (policy_key, shift_id),
    UNIQUE (policy_key, position),
    CHECK (start_time <> end_time)
);
INSERT INTO public.operations_shift_schedule (
    policy_key, shift_id, label, start_time, end_time, position
) VALUES
    ('default', 'day', '주간', '08:00'::time, '20:00'::time, 1),
    ('default', 'night', '야간', '20:00'::time, '08:00'::time, 2)
ON CONFLICT (policy_key, shift_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS public.operations_shift_handover_memos (
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL CHECK (period_end > period_start),
    timezone text NOT NULL CHECK (timezone = 'Asia/Seoul'),
    memo text NOT NULL DEFAULT '' CHECK (char_length(memo) <= 4000),
    updated_by text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (period_start, period_end)
);

CREATE TABLE IF NOT EXISTS public.incident_document_versions (
    document_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    episode_id uuid NOT NULL
        REFERENCES public.anomaly_episodes(episode_id) ON DELETE RESTRICT,
    document_type text NOT NULL CHECK (document_type IN ('work_order', 'incident_report')),
    version integer NOT NULL CHECK (version > 0),
    parent_document_version_id uuid
        REFERENCES public.incident_document_versions(document_version_id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (status IN ('draft', 'ai_reviewed', 'approved', 'failed')),
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object'),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    approved_by text,
    approved_at timestamptz,
    UNIQUE (episode_id, document_type, version),
    CHECK (version = 1 OR parent_document_version_id IS NOT NULL),
    CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS incident_document_versions_episode_idx
    ON public.incident_document_versions(episode_id, document_type, version DESC);

CREATE TABLE IF NOT EXISTS public.incident_document_reviews (
    document_review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id uuid NOT NULL
        REFERENCES public.incident_document_versions(document_version_id) ON DELETE RESTRICT,
    review_type text NOT NULL CHECK (review_type IN ('ai_review', 'operator_note', 'approval')),
    decision text NOT NULL CHECK (decision IN ('pending', 'approved', 'changes_requested', 'failed')),
    note text NOT NULL CHECK (char_length(btrim(note)) BETWEEN 1 AND 4000),
    evidence jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(evidence) = 'array'),
    actor text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS incident_document_reviews_version_idx
    ON public.incident_document_reviews(document_version_id, created_at);

CREATE TABLE IF NOT EXISTS public.operations_report_periods (
    report_period_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type text NOT NULL CHECK (report_type IN ('shift', 'daily')),
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL CHECK (period_end > period_start),
    timezone text NOT NULL CHECK (timezone = 'Asia/Seoul'),
    status text NOT NULL CHECK (status IN ('pending', 'generating', 'official', 'failed', 'overdue')),
    operation_key text NOT NULL UNIQUE,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (report_type, period_start, period_end)
);
CREATE INDEX IF NOT EXISTS operations_report_periods_due_idx
    ON public.operations_report_periods(status, period_end);

CREATE TABLE IF NOT EXISTS public.operations_report_versions (
    report_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_period_id uuid NOT NULL
        REFERENCES public.operations_report_periods(report_period_id) ON DELETE RESTRICT,
    version integer NOT NULL CHECK (version > 0),
    source_report_version_id uuid
        REFERENCES public.operations_report_versions(report_version_id) ON DELETE RESTRICT,
    official boolean NOT NULL DEFAULT false,
    content jsonb NOT NULL CHECK (jsonb_typeof(content) = 'object'),
    content_hash text NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    data_quality_caveats jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(data_quality_caveats) = 'array'),
    generated_by text NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (report_period_id, version),
    CHECK (version = 1 OR source_report_version_id IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS operations_report_versions_one_official_uidx
    ON public.operations_report_versions(report_period_id) WHERE official;

CREATE TABLE IF NOT EXISTS public.operations_report_corrections (
    correction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_report_version_id uuid NOT NULL
        REFERENCES public.operations_report_versions(report_version_id) ON DELETE RESTRICT,
    corrected_report_version_id uuid NOT NULL UNIQUE
        REFERENCES public.operations_report_versions(report_version_id) ON DELETE RESTRICT,
    reason text NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 1 AND 4000),
    created_by text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (source_report_version_id <> corrected_report_version_id)
);

CREATE TABLE IF NOT EXISTS public.operation_idempotency_keys (
    operation_scope text NOT NULL,
    idempotency_key text NOT NULL,
    request_hash text NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    response_payload jsonb CHECK (response_payload IS NULL OR jsonb_typeof(response_payload) = 'object'),
    status text NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    PRIMARY KEY (operation_scope, idempotency_key)
);

CREATE OR REPLACE FUNCTION public.prevent_append_only_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $append_only$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME
        USING ERRCODE = '55000';
END
$append_only$;

DO $append_only_triggers$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'incident_document_versions',
        'incident_document_reviews',
        'operations_report_versions',
        'operations_report_corrections'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1
            FROM pg_trigger
            WHERE tgname = table_name || '_append_only_trigger'
              AND tgrelid = ('public.' || table_name)::regclass
        ) THEN
            EXECUTE format(
                'CREATE TRIGGER %I BEFORE UPDATE OR DELETE ON public.%I '
                'FOR EACH ROW EXECUTE FUNCTION public.prevent_append_only_mutation()',
                table_name || '_append_only_trigger',
                table_name
            );
        END IF;
    END LOOP;
END
$append_only_triggers$;

GRANT SELECT, INSERT, UPDATE ON public.anomaly_episodes, public.preventive_projections,
    public.operations_policy,
    public.operations_shift_handover_memos,
    public.operations_report_periods, public.operation_idempotency_keys TO heatgrid_app;
GRANT SELECT, INSERT ON public.anomaly_episode_consumptions,
    public.anomaly_episode_events TO heatgrid_app;
GRANT USAGE, SELECT ON SEQUENCE public.anomaly_episode_events_event_id_seq TO heatgrid_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.operations_shift_schedule TO heatgrid_app;
GRANT SELECT, INSERT ON public.incident_document_versions, public.incident_document_reviews,
    public.operations_report_versions, public.operations_report_corrections TO heatgrid_app;
REVOKE UPDATE ON public.incident_document_versions, public.incident_document_reviews,
    public.operations_report_versions, public.operations_report_corrections FROM heatgrid_app;
