from __future__ import annotations

import os
import sys
import subprocess
import uuid
import asyncio
import importlib.util
import ast
from pathlib import Path

import asyncpg


def _load_script():
    path = Path(__file__).resolve().parents[1] / "scripts" / "simulate_predictor_db.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("simulate_predictor_db", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError("simulate_predictor_db 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    sys.modules["simulate_predictor_db"] = module
    spec.loader.exec_module(module)
    return module


script = _load_script()
CURRENT_BEST_FEATURES = script.CURRENT_BEST_FEATURES
M1_SPECIALIST_FEATURES = script.M1_SPECIALIST_FEATURES
DEFAULT_DATABASE_URL = script.DEFAULT_DATABASE_URL
normalize_database_url = script.normalize_database_url


def test_predictor_features_do_not_include_validation_fields() -> None:
    feature_columns = set(CURRENT_BEST_FEATURES) | set(M1_SPECIALIST_FEATURES)
    assert "label" not in feature_columns
    assert "fault_label" not in feature_columns
    assert "fault_event_id" not in feature_columns


def _db_url() -> str:
    return normalize_database_url(os.environ.get("HEATGRID_DATABASE_URL", DEFAULT_DATABASE_URL))


def _load_summary(stdout: str) -> dict:
    return ast.literal_eval(stdout.removeprefix("Load complete: ").strip())


def test_simulate_predictor_db_inserts_model_run_and_outputs() -> None:
    model_run_id = uuid.uuid4()
    result = subprocess.run(
        [
            sys.executable,
            "scripts/simulate_predictor_db.py",
            "--model-run-id",
            str(model_run_id),
            "--append",
            "--database-url",
            _db_url(),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr

    async def _check() -> None:
        conn = await asyncpg.connect(_db_url())
        try:
            run_row = await conn.fetchrow(
                "SELECT model_run_id, model_family, model_name, run_type, source_artifact "
                "FROM model_runs WHERE model_run_id = $1",
                model_run_id,
            )
            assert run_row is not None
            assert run_row["model_family"] == "priority_engine"
            assert run_row["model_name"] == "offline_priority_simulator"
            assert run_row["run_type"] == "offline_simulation"
            assert run_row["source_artifact"] == "output/agent_priority_card.csv"

            output_count = await conn.fetchval(
                "SELECT count(*) FROM model_outputs WHERE model_run_id = $1",
                model_run_id,
            )
            assert output_count == 1252
        finally:
            await conn.close()

    asyncio.run(_check())


def test_simulate_predictor_db_enqueues_urgent_high_alerts_once() -> None:
    model_run_id = uuid.uuid4()

    async def _reset_queue() -> None:
        conn = await asyncpg.connect(_db_url())
        try:
            await conn.execute("DROP TABLE IF EXISTS agent_run_artifacts")
            await conn.execute("DROP TABLE IF EXISTS agent_run_events")
            await conn.execute("DROP TABLE IF EXISTS agent_runs")
            await conn.execute("DROP TABLE IF EXISTS ops_alert_queue")
        finally:
            await conn.close()

    asyncio.run(_reset_queue())

    command = [
        sys.executable,
        "scripts/simulate_predictor_db.py",
        "--model-run-id",
        str(model_run_id),
        "--append",
        "--enqueue-alerts",
        "--database-url",
        _db_url(),
    ]
    first = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    second = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr
    assert "'fallback_source': 'csv_windows'" in first.stdout
    first_summary = _load_summary(first.stdout)
    second_summary = _load_summary(second.stdout)

    async def _check() -> None:
        conn = await asyncpg.connect(_db_url())
        try:
            expected = await conn.fetchval(
                "SELECT count(*) "
                "FROM priority_decisions "
                "WHERE lower(priority_level) IN ('urgent', 'high')"
            )
            actual = await conn.fetchval("SELECT count(*) FROM ops_alert_queue")
            non_priority = await conn.fetchval(
                "SELECT count(*) "
                "FROM ops_alert_queue "
                "WHERE lower(priority_level) NOT IN ('urgent', 'high')"
            )
            duplicate_cards = await conn.fetchval(
                "SELECT count(*) "
                "FROM ("
                "SELECT card_id FROM ops_alert_queue GROUP BY card_id HAVING count(*) > 1"
                ") duplicated"
            )
            score_type = await conn.fetchval(
                "SELECT data_type "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name = 'ops_alert_queue' "
                "AND column_name = 'priority_score'"
            )
            assert actual == expected
            assert non_priority == 0
            assert duplicate_cards == 0
            assert score_type == "double precision"
            assert first_summary["alerts"]["queued_count"] == expected
            assert first_summary["alerts"]["existing_count"] == 0
            assert second_summary["alerts"]["queued_count"] == 0
            assert second_summary["alerts"]["existing_count"] == expected
        finally:
            await conn.close()

    asyncio.run(_check())
