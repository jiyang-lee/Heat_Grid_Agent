from __future__ import annotations

import asyncpg


REQUIRED_TABLES = (
    "substations",
    "windows",
    "model_feature_snapshots",
    "model_runs",
    "model_outputs",
    "priority_decisions",
    "priority_cards",
    "sensor_summaries",
    "priority_card_review_reasons",
    "priority_evaluation_runs",
    "priority_evaluation_results",
)


async def ensure_target_schema(conn: asyncpg.Connection) -> None:
    missing = [
        table
        for table in REQUIRED_TABLES
        if not await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table}")
    ]
    if missing:
        raise RuntimeError(f"database migrations have not created tables: {missing}")
