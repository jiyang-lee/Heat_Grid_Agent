COMMENT ON SCHEMA public IS 'HeatGrid schema frozen at version 010';

ALTER TABLE public.agent_run_reviews
    ADD COLUMN next_action text NOT NULL DEFAULT 'none';
ALTER TABLE public.agent_run_reviews
    DROP CONSTRAINT IF EXISTS agent_run_reviews_decision_check;
ALTER TABLE public.agent_run_reviews
    ADD CONSTRAINT agent_run_reviews_decision_check
    CHECK (decision IN ('approve', 'reject', 'correct', 'keep_human_review'));
ALTER TABLE public.agent_run_reviews
    ADD CONSTRAINT agent_run_reviews_next_action_check
    CHECK (next_action IN (
        'none', 'targeted_rerun', 'manual_investigation', 'close_without_rerun'
    ));
ALTER TABLE public.agent_run_reviews
    ADD CONSTRAINT agent_run_reviews_reject_reason_check
    CHECK (decision <> 'reject' OR reason_category IS NOT NULL);
ALTER TABLE public.agent_run_reviews
    ADD CONSTRAINT agent_run_reviews_targeted_rerun_reason_check
    CHECK (next_action <> 'targeted_rerun' OR reason_category IS NOT NULL);

CREATE TABLE public.review_chat_threads (
    thread_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    status text NOT NULL CHECK (status IN ('open', 'closed', 'archived')),
    created_by text NOT NULL,
    base_review_version integer NOT NULL DEFAULT 0 CHECK (base_review_version >= 0),
    base_review_snapshot_hash text,
    base_output_hash text NOT NULL CHECK (base_output_hash ~ '^[0-9a-f]{64}$'),
    context_hash text NOT NULL CHECK (context_hash ~ '^[0-9a-f]{64}$'),
    model_name text,
    prompt_version text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    closed_at timestamptz
);
CREATE UNIQUE INDEX review_chat_threads_one_open_per_run
    ON public.review_chat_threads(run_id) WHERE status = 'open';

CREATE TABLE public.review_chat_messages (
    message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id uuid NOT NULL REFERENCES public.review_chat_threads(thread_id) ON DELETE RESTRICT,
    sequence integer NOT NULL CHECK (sequence > 0),
    role text NOT NULL CHECK (role IN ('system_event', 'operator', 'assistant')),
    message_kind text NOT NULL CHECK (message_kind IN (
        'question', 'explanation', 'action_request', 'action_proposal',
        'confirmation', 'execution_result', 'error'
    )),
    content text NOT NULL CHECK (char_length(content) BETWEEN 1 AND 8000),
    structured_payload jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(structured_payload) = 'object'),
    citations jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(citations) = 'array'),
    context_hash text NOT NULL CHECK (context_hash ~ '^[0-9a-f]{64}$'),
    model_name text,
    prompt_version text,
    token_usage jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(token_usage) = 'object'),
    idempotency_key text,
    message_hash text NOT NULL CHECK (message_hash ~ '^[0-9a-f]{64}$'),
    created_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (thread_id, sequence)
);
CREATE UNIQUE INDEX review_chat_messages_idempotency_uidx
    ON public.review_chat_messages(thread_id, idempotency_key)
    WHERE idempotency_key IS NOT NULL;

CREATE TABLE public.review_chat_action_proposals (
    proposal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id uuid NOT NULL REFERENCES public.review_chat_threads(thread_id) ON DELETE RESTRICT,
    source_message_id uuid NOT NULL REFERENCES public.review_chat_messages(message_id) ON DELETE RESTRICT,
    run_id uuid NOT NULL REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    expected_review_version integer NOT NULL CHECK (expected_review_version >= 0),
    context_hash text NOT NULL CHECK (context_hash ~ '^[0-9a-f]{64}$'),
    proposal_hash text NOT NULL UNIQUE CHECK (proposal_hash ~ '^[0-9a-f]{64}$'),
    status text NOT NULL CHECK (status IN (
        'draft', 'awaiting_confirmation', 'confirmed', 'executing', 'executed',
        'cancelled', 'expired', 'stale', 'conflict', 'failed'
    )),
    decision text NOT NULL CHECK (decision IN ('approve', 'reject', 'correct', 'keep_human_review')),
    next_action text NOT NULL CHECK (next_action IN (
        'none', 'targeted_rerun', 'manual_investigation', 'close_without_rerun'
    )),
    reason text NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 1 AND 2000),
    reason_category text,
    disposition text,
    correction jsonb,
    evidence_annotations jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(evidence_annotations) = 'array'),
    operator_labels jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(operator_labels) = 'array'),
    parser_confidence double precision CHECK (
        parser_confidence IS NULL OR (parser_confidence >= 0 AND parser_confidence <= 1)
    ),
    ambiguity_reasons jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(ambiguity_reasons) = 'array'),
    confirmed_by text,
    confirmed_at timestamptz,
    executed_review_id uuid REFERENCES public.agent_run_reviews(review_id) ON DELETE RESTRICT,
    child_run_id uuid REFERENCES public.agent_runs(run_id) ON DELETE RESTRICT,
    execution_error text,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT review_chat_action_proposals_reject_reason_check
        CHECK (decision <> 'reject' OR reason_category IS NOT NULL),
    CONSTRAINT review_chat_action_proposals_targeted_rerun_reason_check
        CHECK (next_action <> 'targeted_rerun' OR reason_category IS NOT NULL),
    CONSTRAINT review_chat_action_proposals_correction_check
        CHECK (correction IS NULL OR jsonb_typeof(correction) = 'object')
);
CREATE INDEX review_chat_action_proposals_thread_idx
    ON public.review_chat_action_proposals(thread_id, created_at DESC);

CREATE TABLE public.review_chat_events (
    event_id bigserial PRIMARY KEY,
    thread_id uuid NOT NULL REFERENCES public.review_chat_threads(thread_id) ON DELETE RESTRICT,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(payload) = 'object'),
    operation_key text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX review_chat_events_operation_uidx
    ON public.review_chat_events(operation_key) WHERE operation_key IS NOT NULL;
CREATE INDEX review_chat_events_thread_idx
    ON public.review_chat_events(thread_id, event_id);

GRANT SELECT, INSERT, UPDATE ON public.review_chat_threads, public.review_chat_messages,
    public.review_chat_action_proposals, public.review_chat_events TO heatgrid_app;
GRANT USAGE, SELECT ON SEQUENCE public.review_chat_events_event_id_seq TO heatgrid_app;
