from __future__ import annotations

from typing import Final

import asyncpg

TARGET_SCHEMA_DDL: Final = (
    """
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
    )
    """,
    """
    ALTER TABLE demo_replay_runs
    ADD COLUMN IF NOT EXISTS has_scored_window boolean NOT NULL DEFAULT false
    """,
    """
    ALTER TABLE demo_replay_runs
    ADD COLUMN IF NOT EXISTS last_evaluation_run_id uuid
    """,
    """
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
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS demo_replay_runs_state_idx
    ON demo_replay_runs(state, updated_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS sensor_readings_time_idx
    ON sensor_readings(run_id, simulated_at, substation_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS sensor_readings_substation_idx
    ON sensor_readings(substation_id, simulated_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS windows (
        window_id uuid PRIMARY KEY,
        manufacturer_id text NOT NULL,
        substation_id integer,
        window_start timestamptz NOT NULL,
        window_end timestamptz NOT NULL,
        source_file text,
        season_bucket text,
        label text,
        fault_event_id text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS substations (
        manufacturer_id text NOT NULL,
        substation_id integer NOT NULL,
        configuration_type text,
        PRIMARY KEY (manufacturer_id, substation_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_feature_snapshots (
        window_id uuid PRIMARY KEY REFERENCES windows(window_id) ON DELETE CASCADE,
        feature_set_version text NOT NULL,
        features jsonb NOT NULL,
        source_artifacts jsonb NOT NULL DEFAULT '[]'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS priority_decisions (
        priority_decision_id uuid PRIMARY KEY,
        window_id uuid NOT NULL REFERENCES windows(window_id) ON DELETE CASCADE,
        current_best_priority_score double precision,
        current_best_priority_level text,
        m1_specialist_priority_score double precision,
        m1_specialist_priority_level text,
        priority_score double precision,
        priority_level text,
        priority_source text,
        m1_priority_agreement text,
        policy_version text,
        current_best_weight double precision,
        m1_specialist_weight double precision,
        decision_basis text,
        m1_specialist_primary_state text,
        m1_specialist_fault_group text,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS priority_cards (
        card_id uuid PRIMARY KEY,
        priority_decision_id uuid NOT NULL
            REFERENCES priority_decisions(priority_decision_id) ON DELETE CASCADE,
        operational_label text,
        primary_state text,
        review_required boolean,
        trust_level text,
        why_reason text,
        recommended_action text,
        first_crossing_time timestamptz,
        stable_crossing_time timestamptz,
        stable_crossing_lead_hours double precision,
        raw_card jsonb,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sensor_summaries (
        sensor_summary_id uuid PRIMARY KEY,
        card_id uuid NOT NULL REFERENCES priority_cards(card_id) ON DELETE CASCADE,
        window_id uuid NOT NULL REFERENCES windows(window_id) ON DELETE CASCADE,
        flow_source text NOT NULL,
        model_id text,
        model_version text,
        source_artifact text,
        selection_rule text,
        feature_name text NOT NULL,
        source_sensor text,
        source_column text,
        meaning text,
        unit text,
        calculation text,
        feature_value double precision,
        display_rank integer NOT NULL,
        summary_text text
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS priority_card_review_reasons (
        card_id uuid NOT NULL REFERENCES priority_cards(card_id) ON DELETE CASCADE,
        reason_code text NOT NULL,
        display_rank integer NOT NULL,
        PRIMARY KEY (card_id, reason_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_runs (
        model_run_id uuid PRIMARY KEY,
        model_family text NOT NULL,
        model_name text NOT NULL,
        model_version text,
        run_type text,
        source_artifact text,
        created_at timestamptz NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS model_outputs (
        model_output_id uuid PRIMARY KEY,
        window_id uuid NOT NULL REFERENCES windows(window_id) ON DELETE CASCADE,
        model_run_id uuid NOT NULL REFERENCES model_runs(model_run_id) ON DELETE CASCADE,
        model_family text NOT NULL,
        score_name text,
        score_value double precision,
        label_name text,
        label_value text,
        display_rank integer NOT NULL
    )
    """,
    """
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
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS priority_evaluation_results (
        evaluation_result_id uuid PRIMARY KEY,
        evaluation_run_id uuid NOT NULL
            REFERENCES priority_evaluation_runs(evaluation_run_id) ON DELETE CASCADE,
        manufacturer_id text NOT NULL,
        substation_id integer NOT NULL,
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
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS priority_evaluation_one_active_idx
    ON priority_evaluation_runs(is_active) WHERE is_active
    """,
    """
    CREATE INDEX IF NOT EXISTS priority_evaluation_completed_idx
    ON priority_evaluation_runs(status, as_of_time DESC, completed_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS priority_evaluation_result_rank_idx
    ON priority_evaluation_results(evaluation_run_id, rank_included, priority_rank)
    """,
    """
    CREATE INDEX IF NOT EXISTS priority_evaluation_result_substation_idx
    ON priority_evaluation_results(manufacturer_id, substation_id, evaluation_run_id)
    """,
)


async def ensure_target_schema(conn: asyncpg.Connection) -> None:
    for statement in TARGET_SCHEMA_DDL:
        await conn.execute(statement)
