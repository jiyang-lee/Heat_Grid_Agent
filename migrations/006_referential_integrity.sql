DO $agent_referential_integrity$
BEGIN
    IF to_regclass('public.ops_alert_queue') IS NOT NULL
       AND to_regclass('public.priority_evaluation_runs') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'ops_alert_queue_evaluation_run_id_fkey'
             AND conrelid = 'public.ops_alert_queue'::regclass
       ) THEN
        ALTER TABLE public.ops_alert_queue
        ADD CONSTRAINT ops_alert_queue_evaluation_run_id_fkey
        FOREIGN KEY (evaluation_run_id)
        REFERENCES public.priority_evaluation_runs(evaluation_run_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;

    IF to_regclass('public.agent_runs') IS NOT NULL
       AND to_regclass('public.priority_evaluation_runs') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'agent_runs_evaluation_run_id_fkey'
             AND conrelid = 'public.agent_runs'::regclass
       ) THEN
        ALTER TABLE public.agent_runs
        ADD CONSTRAINT agent_runs_evaluation_run_id_fkey
        FOREIGN KEY (evaluation_run_id)
        REFERENCES public.priority_evaluation_runs(evaluation_run_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'priority_evaluation_results_source_window_id_fkey'
          AND conrelid = 'public.priority_evaluation_results'::regclass
    ) THEN
        ALTER TABLE public.priority_evaluation_results
        ADD CONSTRAINT priority_evaluation_results_source_window_id_fkey
        FOREIGN KEY (source_window_id) REFERENCES public.windows(window_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'priority_evaluation_results_source_card_id_fkey'
          AND conrelid = 'public.priority_evaluation_results'::regclass
    ) THEN
        ALTER TABLE public.priority_evaluation_results
        ADD CONSTRAINT priority_evaluation_results_source_card_id_fkey
        FOREIGN KEY (source_card_id) REFERENCES public.priority_cards(card_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'priority_evaluation_results_source_priority_decision_id_fkey'
          AND conrelid = 'public.priority_evaluation_results'::regclass
    ) THEN
        ALTER TABLE public.priority_evaluation_results
        ADD CONSTRAINT priority_evaluation_results_source_priority_decision_id_fkey
        FOREIGN KEY (source_priority_decision_id)
        REFERENCES public.priority_decisions(priority_decision_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'agent_loop_iterations_run_id_fkey'
          AND conrelid = 'public.agent_loop_iterations'::regclass
    ) THEN
        ALTER TABLE public.agent_loop_iterations
        ADD CONSTRAINT agent_loop_iterations_run_id_fkey
        FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;

    IF to_regclass('public.ops_alert_queue') IS NOT NULL
       AND to_regclass('public.substations') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'ops_alert_queue_substation_fkey'
             AND conrelid = 'public.ops_alert_queue'::regclass
       ) THEN
        ALTER TABLE public.ops_alert_queue
        ADD CONSTRAINT ops_alert_queue_substation_fkey
        FOREIGN KEY (manufacturer_id, substation_id)
        REFERENCES public.substations(manufacturer_id, substation_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;

    IF to_regclass('public.agent_runs') IS NOT NULL
       AND to_regclass('public.substations') IS NOT NULL
       AND NOT EXISTS (
           SELECT 1
           FROM pg_constraint
           WHERE conname = 'agent_runs_substation_fkey'
             AND conrelid = 'public.agent_runs'::regclass
       ) THEN
        ALTER TABLE public.agent_runs
        ADD CONSTRAINT agent_runs_substation_fkey
        FOREIGN KEY (manufacturer_id, substation_id)
        REFERENCES public.substations(manufacturer_id, substation_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;
END
$agent_referential_integrity$;

DO $agent_review_restrict$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'agent_run_reviews_run_id_fkey'
          AND conrelid = 'public.agent_run_reviews'::regclass
          AND confdeltype = 'c'
    ) THEN
        ALTER TABLE public.agent_run_reviews
        DROP CONSTRAINT agent_run_reviews_run_id_fkey;
        ALTER TABLE public.agent_run_reviews
        ADD CONSTRAINT agent_run_reviews_run_id_fkey
        FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'agent_run_review_snapshots_run_id_fkey'
          AND conrelid = 'public.agent_run_review_snapshots'::regclass
          AND confdeltype = 'c'
    ) THEN
        ALTER TABLE public.agent_run_review_snapshots
        DROP CONSTRAINT agent_run_review_snapshots_run_id_fkey;
        ALTER TABLE public.agent_run_review_snapshots
        ADD CONSTRAINT agent_run_review_snapshots_run_id_fkey
        FOREIGN KEY (run_id) REFERENCES public.agent_runs(run_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'agent_policy_candidates_source_review_id_fkey'
          AND conrelid = 'public.agent_policy_candidates'::regclass
          AND confdeltype = 'c'
    ) THEN
        ALTER TABLE public.agent_policy_candidates
        DROP CONSTRAINT agent_policy_candidates_source_review_id_fkey;
        ALTER TABLE public.agent_policy_candidates
        ADD CONSTRAINT agent_policy_candidates_source_review_id_fkey
        FOREIGN KEY (source_review_id)
        REFERENCES public.agent_run_reviews(review_id)
        ON DELETE RESTRICT NOT VALID;
    END IF;
END
$agent_review_restrict$;

DO $agent_validate_constraints$
DECLARE
    constraint_row record;
BEGIN
    FOR constraint_row IN
        SELECT n.nspname AS schema_name, c.relname AS table_name, pc.conname
        FROM pg_constraint pc
        JOIN pg_class c ON c.oid = pc.conrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE pc.conname IN (
            'ops_alert_queue_evaluation_run_id_fkey',
            'agent_runs_evaluation_run_id_fkey',
            'ops_alert_queue_substation_fkey',
            'agent_runs_substation_fkey',
            'priority_evaluation_results_source_window_id_fkey',
            'priority_evaluation_results_source_card_id_fkey',
            'priority_evaluation_results_source_priority_decision_id_fkey',
            'agent_loop_iterations_run_id_fkey',
            'agent_run_reviews_run_id_fkey',
            'agent_run_review_snapshots_run_id_fkey',
            'agent_policy_candidates_source_review_id_fkey'
        )
        AND NOT pc.convalidated
    LOOP
        EXECUTE format(
            'ALTER TABLE %I.%I VALIDATE CONSTRAINT %I',
            constraint_row.schema_name,
            constraint_row.table_name,
            constraint_row.conname
        );
    END LOOP;
END
$agent_validate_constraints$;

DROP TABLE IF EXISTS public.ops_retrieval_hits;
DROP TABLE IF EXISTS public.ops_tool_calls;
DROP TABLE IF EXISTS public.ops_agent_runs;
