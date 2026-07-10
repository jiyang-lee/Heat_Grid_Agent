from __future__ import annotations

from typing import Final

import asyncpg

TARGET_SCHEMA_DDL: Final = (
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
)


async def ensure_target_schema(conn: asyncpg.Connection) -> None:
    for statement in TARGET_SCHEMA_DDL:
        await conn.execute(statement)
