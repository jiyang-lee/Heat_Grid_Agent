CREATE TABLE IF NOT EXISTS agent_run_tasks (
    task_id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    task_key text NOT NULL,
    operation_key text NOT NULL,
    parent_task_id uuid REFERENCES agent_run_tasks(task_id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued', 'running', 'completed', 'failed')),
    checkpoint_thread_id text NOT NULL,
    checkpoint_namespace text NOT NULL DEFAULT '',
    checkpoint_id text,
    lease_owner uuid,
    lease_expires_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    input_snapshot jsonb,
    output_snapshot jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (run_id, task_key),
    UNIQUE (operation_key)
);

CREATE INDEX IF NOT EXISTS agent_run_tasks_reclaim_idx
ON agent_run_tasks(status, lease_expires_at)
WHERE status IN ('queued', 'running');

CREATE TABLE IF NOT EXISTS agent_budget_ledger (
    ledger_id uuid PRIMARY KEY,
    run_id uuid NOT NULL,
    task_id uuid REFERENCES agent_run_tasks(task_id) ON DELETE CASCADE,
    parent_ledger_id uuid REFERENCES agent_budget_ledger(ledger_id) ON DELETE CASCADE,
    operation_key text NOT NULL UNIQUE,
    status text NOT NULL DEFAULT 'reserved'
        CHECK (status IN ('reserved', 'settled', 'released')),
    token_limit integer NOT NULL CHECK (token_limit > 0),
    tokens_used integer CHECK (
        tokens_used IS NULL OR (tokens_used >= 0 AND tokens_used <= token_limit)
    ),
    retry_limit integer NOT NULL DEFAULT 3 CHECK (retry_limit >= 0),
    external_search_limit integer NOT NULL DEFAULT 0
        CHECK (external_search_limit = 0),
    external_search_used integer NOT NULL DEFAULT 0
        CHECK (external_search_used = 0),
    reserved_at timestamptz NOT NULL DEFAULT now(),
    settled_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_budget_ledger_run_idx
ON agent_budget_ledger(run_id, reserved_at);

ALTER TABLE agent_budget_ledger
DROP CONSTRAINT IF EXISTS agent_budget_ledger_tokens_used_check;

ALTER TABLE agent_budget_ledger
ADD CONSTRAINT agent_budget_ledger_tokens_used_check
CHECK (tokens_used IS NULL OR (tokens_used >= 0 AND tokens_used <= token_limit));

DO $$
BEGIN
    IF to_regclass('public.agent_runs') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'agent_run_tasks_run_id_fkey'
             AND conrelid = 'agent_run_tasks'::regclass
       ) THEN
        ALTER TABLE agent_run_tasks
        ADD CONSTRAINT agent_run_tasks_run_id_fkey
        FOREIGN KEY (run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE;
    END IF;

    IF to_regclass('public.agent_runs') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1 FROM pg_constraint
           WHERE conname = 'agent_budget_ledger_run_id_fkey'
             AND conrelid = 'agent_budget_ledger'::regclass
       ) THEN
        ALTER TABLE agent_budget_ledger
        ADD CONSTRAINT agent_budget_ledger_run_id_fkey
        FOREIGN KEY (run_id) REFERENCES agent_runs(run_id) ON DELETE CASCADE;
    END IF;

    IF to_regclass('public.agent_run_events') IS NOT NULL THEN
        ALTER TABLE agent_run_events ADD COLUMN IF NOT EXISTS operation_key text;
        CREATE UNIQUE INDEX IF NOT EXISTS agent_run_events_operation_key_uidx
        ON agent_run_events(operation_key) WHERE operation_key IS NOT NULL;
    END IF;

    IF to_regclass('public.agent_loop_iterations') IS NOT NULL THEN
        DELETE FROM agent_loop_iterations duplicate
        USING agent_loop_iterations kept
        WHERE duplicate.run_id = kept.run_id
          AND duplicate.iteration = kept.iteration
          AND duplicate.phase = kept.phase
          AND duplicate.iteration_id > kept.iteration_id;
        CREATE UNIQUE INDEX IF NOT EXISTS agent_loop_iterations_run_iteration_phase_uidx
        ON agent_loop_iterations(run_id, iteration, phase);
    END IF;

    IF to_regclass('public.human_review_tasks') IS NOT NULL THEN
        ALTER TABLE human_review_tasks ADD COLUMN IF NOT EXISTS operation_key text;
        CREATE UNIQUE INDEX IF NOT EXISTS human_review_tasks_operation_key_uidx
        ON human_review_tasks(operation_key) WHERE operation_key IS NOT NULL;
    END IF;
    IF to_regclass('public.agent_runs') IS NOT NULL THEN
        INSERT INTO agent_run_tasks (
            task_id,
            run_id,
            task_key,
            operation_key,
            status,
            checkpoint_thread_id
        )
        SELECT
            gen_random_uuid(),
            run_id,
            'agent_graph:v1',
            'agent-graph:' || run_id::text,
            'queued',
            run_id::text
        FROM agent_runs
        WHERE status IN ('queued', 'running')
        ON CONFLICT (run_id, task_key) DO NOTHING;
    END IF;
END
$$;
