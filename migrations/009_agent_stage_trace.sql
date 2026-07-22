COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 009';

CREATE TABLE public.agent_model_calls (
    model_call_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    stage_snapshot_id uuid,
    stage_name text NOT NULL CHECK (stage_name IN (
        'ml_validation', 'weather_context', 'rag_retrieval', 'rag_interpretation',
        'fault_analysis', 'higher_model_reassessment', 'parent_disposition',
        'report_draft', 'report_fidelity'
    )),
    stage_attempt integer NOT NULL CHECK (stage_attempt > 0),
    execution_profile text NOT NULL,
    purpose text NOT NULL,
    model_name text NOT NULL,
    status text NOT NULL CHECK (status IN (
        'running', 'completed', 'failed', 'budget_exceeded', 'policy_denied'
    )),
    input_hash text NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
    snapshot_bundle_hash text,
    output_hash text,
    allowed_tools jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(allowed_tools) = 'array'),
    max_total_tool_calls integer NOT NULL CHECK (max_total_tool_calls >= 0),
    max_model_turns integer NOT NULL CHECK (max_model_turns > 0),
    actual_tool_calls integer NOT NULL DEFAULT 0 CHECK (actual_tool_calls >= 0),
    actual_model_turns integer NOT NULL DEFAULT 0 CHECK (actual_model_turns >= 0),
    input_tokens integer NOT NULL DEFAULT 0,
    cached_input_tokens integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    total_tokens integer NOT NULL DEFAULT 0,
    latency_ms integer,
    error_type text,
    error_message text,
    operation_key text NOT NULL UNIQUE,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    CONSTRAINT agent_model_calls_stage_snapshot_id_fkey
        FOREIGN KEY (stage_snapshot_id)
        REFERENCES public.agent_stage_snapshots(stage_snapshot_id) ON DELETE RESTRICT
);
CREATE INDEX agent_model_calls_run_stage_idx
    ON public.agent_model_calls(run_id, stage_name, stage_attempt);

CREATE TABLE public.agent_tool_calls (
    tool_call_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    model_call_id uuid NOT NULL
        REFERENCES public.agent_model_calls(model_call_id) ON DELETE RESTRICT,
    run_id uuid NOT NULL REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    stage_name text NOT NULL,
    call_sequence integer NOT NULL CHECK (call_sequence > 0),
    tool_name text NOT NULL,
    status text NOT NULL CHECK (status IN (
        'running', 'completed', 'failed', 'reused',
        'policy_denied', 'duplicate_blocked', 'budget_exhausted'
    )),
    args_hash text NOT NULL CHECK (args_hash ~ '^[0-9a-f]{64}$'),
    result_hash text,
    args_size integer NOT NULL DEFAULT 0,
    result_size integer NOT NULL DEFAULT 0,
    duration_ms integer,
    error_type text,
    error_message text,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (model_call_id, call_sequence)
);
CREATE INDEX agent_tool_calls_run_stage_idx
    ON public.agent_tool_calls(run_id, stage_name, started_at);

GRANT SELECT, INSERT, UPDATE ON public.agent_model_calls, public.agent_tool_calls
    TO heatgrid_app;
