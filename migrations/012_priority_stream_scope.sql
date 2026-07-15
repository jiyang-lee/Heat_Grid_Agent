COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 012';

ALTER TABLE public.priority_evaluation_runs
    ADD COLUMN IF NOT EXISTS stream_key text NOT NULL DEFAULT 'default';
ALTER TABLE public.priority_evaluation_runs
    ADD COLUMN IF NOT EXISTS source_kind text NOT NULL DEFAULT 'batch';
ALTER TABLE public.priority_evaluation_runs
    ADD COLUMN IF NOT EXISTS source_run_id uuid;
ALTER TABLE public.priority_evaluation_runs
    ADD COLUMN IF NOT EXISTS source_dataset_version text;
ALTER TABLE public.priority_evaluation_runs
    DROP CONSTRAINT IF EXISTS priority_evaluation_runs_source_kind_check;
ALTER TABLE public.priority_evaluation_runs
    ADD CONSTRAINT priority_evaluation_runs_source_kind_check
    CHECK (source_kind IN ('batch', 'replay', 'live', 'manual'));
UPDATE public.priority_evaluation_runs
    SET stream_key = 'default', source_kind = 'batch'
    WHERE stream_key IS NULL OR source_kind IS NULL;
DROP INDEX IF EXISTS public.priority_evaluation_one_active_idx;
CREATE UNIQUE INDEX IF NOT EXISTS priority_evaluation_one_active_per_stream_idx
    ON public.priority_evaluation_runs(stream_key) WHERE is_active;
CREATE INDEX IF NOT EXISTS priority_evaluation_stream_completed_idx
    ON public.priority_evaluation_runs(stream_key, status, as_of_time DESC, completed_at DESC);

ALTER TABLE public.ops_alert_queue
    ADD COLUMN IF NOT EXISTS stream_key text NOT NULL DEFAULT 'default';
ALTER TABLE public.ops_alert_queue
    ADD COLUMN IF NOT EXISTS synthetic boolean NOT NULL DEFAULT false;
ALTER TABLE public.ops_alert_queue
    ADD COLUMN IF NOT EXISTS replay_run_id uuid;
ALTER TABLE public.ops_alert_queue
    DROP CONSTRAINT IF EXISTS ops_alert_queue_replay_run_id_fkey;
ALTER TABLE public.ops_alert_queue
    ADD CONSTRAINT ops_alert_queue_replay_run_id_fkey
    FOREIGN KEY (replay_run_id) REFERENCES public.replay_runs(run_id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS ops_alert_queue_stream_status_idx
    ON public.ops_alert_queue(stream_key, status, priority_score DESC);
