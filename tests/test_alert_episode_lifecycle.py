from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
DATABASE_URL = os.getenv("HEATGRID_REPLAY_TEST_DATABASE_URL")
ADMIN_DATABASE_URL = os.getenv("HEATGRID_REPLAY_ADMIN_TEST_DATABASE_URL")
sys.path.insert(0, str(BACKEND))


def test_episode_policy_counts_anomaly_and_recovery_without_leadtime() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.alert_episode_policy import (
        EpisodeSnapshot,
        Observation,
        transition_episode,
    )

    # Given: no active episode and the backend policy of 2 anomaly / 3 recovery.
    empty = EpisodeSnapshot.empty()

    # When: one ordinary anomaly arrives.
    pending = transition_episode(
        empty,
        Observation.anomaly(severity="high"),
        anomaly_confirmations=2,
        recovery_confirmations=3,
    )

    # Then: the episode is pending and no alert should exist yet.
    assert pending.status == "pending"
    assert pending.action == "pending"
    assert pending.anomaly_count == 1
    assert pending.opens_alert is False

    # When: a second ordinary anomaly arrives.
    opened = transition_episode(
        pending.snapshot,
        Observation.anomaly(severity="high"),
        anomaly_confirmations=2,
        recovery_confirmations=3,
    )

    # Then: exactly the second anomaly opens the alert.
    assert opened.status == "open"
    assert opened.action == "opened"
    assert opened.opens_alert is True

    # When: only two normal ticks arrive.
    normal_1 = transition_episode(
        opened.snapshot,
        Observation.normal(),
        anomaly_confirmations=2,
        recovery_confirmations=3,
    )
    normal_2 = transition_episode(
        normal_1.snapshot,
        Observation.normal(),
        anomaly_confirmations=2,
        recovery_confirmations=3,
    )

    # Then: the alert is still open.
    assert normal_2.status == "open"
    assert normal_2.action == "unchanged"

    # When: the third normal tick arrives.
    resolved = transition_episode(
        normal_2.snapshot,
        Observation.normal(),
        anomaly_confirmations=2,
        recovery_confirmations=3,
    )

    # Then: backend recovery resolves the episode.
    assert resolved.status == "resolved"
    assert resolved.action == "resolved"


def test_episode_policy_opens_critical_immediately_and_freezes_bad_data() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.alert_episode_policy import (
        EpisodeSnapshot,
        Observation,
        transition_episode,
    )

    # Given: no active episode.
    empty = EpisodeSnapshot.empty()

    # When: a critical anomaly arrives.
    critical = transition_episode(
        empty,
        Observation.anomaly(severity="critical"),
        anomaly_confirmations=2,
        recovery_confirmations=3,
    )

    # Then: it opens immediately.
    assert critical.status == "open"
    assert critical.action == "opened"
    assert critical.opens_alert is True

    # When: stale, missing, or failed evaluation data arrives.
    frozen = transition_episode(
        critical.snapshot,
        Observation.freeze(),
        anomaly_confirmations=2,
        recovery_confirmations=3,
    )

    # Then: lifecycle counters and open state do not move.
    assert frozen.status == "open"
    assert frozen.action == "frozen"
    assert frozen.snapshot == critical.snapshot


requires_replay_database = pytest.mark.skipif(
    DATABASE_URL is None or ADMIN_DATABASE_URL is None,
    reason="HEATGRID_REPLAY_TEST_DATABASE_URL and HEATGRID_REPLAY_ADMIN_TEST_DATABASE_URL are required",
)


@requires_replay_database
@pytest.mark.anyio
async def test_episode_repository_consumes_evaluations_once_and_separates_preventive() -> None:
    from simulator.versions.v2_postgres_react_ops.backend.alert_episode_repository import (
        consume_evaluation,
        list_preventive_candidates,
    )

    engine = create_async_engine(str(DATABASE_URL))
    cleanup_engine = create_async_engine(str(ADMIN_DATABASE_URL))
    stream_key = f"pytest:{uuid4()}"
    manufacturer_id = "pytest-manufacturer"
    substation_id = 9001
    card_id = str(uuid4())
    now = datetime(2026, 7, 19, 1, 0, tzinfo=UTC)
    try:
        async with engine.begin() as connection:
            await _insert_priority_fixture(
                connection,
                manufacturer_id=manufacturer_id,
                substation_id=substation_id,
                card_id=card_id,
            )
            first = await _insert_evaluation(
                connection,
                stream_key=stream_key,
                manufacturer_id=manufacturer_id,
                substation_id=substation_id,
                card_id=card_id,
                as_of_time=now,
                anomaly_label=True,
                priority_level="high",
            )
            second = await _insert_evaluation(
                connection,
                stream_key=stream_key,
                manufacturer_id=manufacturer_id,
                substation_id=substation_id,
                card_id=card_id,
                as_of_time=now,
                anomaly_label=True,
                priority_level="high",
            )
            preventive = await _insert_evaluation(
                connection,
                stream_key=stream_key,
                manufacturer_id=manufacturer_id,
                substation_id=substation_id,
                card_id=card_id,
                as_of_time=now,
                anomaly_label=False,
                priority_level="urgent",
            )

        first_delta = await consume_evaluation(engine, first)
        second_delta = await consume_evaluation(engine, second)
        duplicate_delta = await consume_evaluation(engine, second)
        await consume_evaluation(engine, preventive)
        watchlist = await list_preventive_candidates(engine, stream_key=stream_key)

        async with engine.connect() as connection:
            alert_count = await connection.scalar(
                text(
                    "SELECT count(*) FROM ops_alert_queue "
                    "WHERE stream_key = :stream_key AND status = 'open'"
                ),
                {"stream_key": stream_key},
            )

        assert first_delta["opened"] == 0
        assert second_delta["opened"] == 1
        assert duplicate_delta["skipped"] == 1
        assert alert_count == 1
        assert len(watchlist) == 1
        assert watchlist[0]["priority_level"] == "urgent"
    finally:
        async with cleanup_engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM preventive_projections WHERE manufacturer_id = :manufacturer_id"),
                {"manufacturer_id": manufacturer_id},
            )
            await connection.execute(
                text("DELETE FROM ops_alert_queue WHERE manufacturer_id = :manufacturer_id"),
                {"manufacturer_id": manufacturer_id},
            )
            await connection.execute(
                text("DELETE FROM anomaly_episode_events WHERE manufacturer_id = :manufacturer_id"),
                {"manufacturer_id": manufacturer_id},
            )
            await connection.execute(
                text(
                    "DELETE FROM anomaly_episode_consumptions WHERE evaluation_run_id IN ("
                    "SELECT evaluation_run_id FROM priority_evaluation_results "
                    "WHERE manufacturer_id = :manufacturer_id)"
                ),
                {"manufacturer_id": manufacturer_id},
            )
            await connection.execute(
                text("DELETE FROM anomaly_episodes WHERE manufacturer_id = :manufacturer_id"),
                {"manufacturer_id": manufacturer_id},
            )
            await connection.execute(
                text(
                    "DELETE FROM priority_evaluation_results "
                    "WHERE manufacturer_id = :manufacturer_id"
                ),
                {"manufacturer_id": manufacturer_id},
            )
            await connection.execute(
                text("DELETE FROM priority_evaluation_runs WHERE stream_key LIKE 'pytest:%'"),
            )
            await connection.execute(
                text(
                    "DELETE FROM priority_cards WHERE priority_decision_id IN ("
                    "SELECT priority_decision_id FROM priority_decisions "
                    "WHERE window_id IN (SELECT window_id FROM windows "
                    "WHERE manufacturer_id = :manufacturer_id))"
                ),
                {"manufacturer_id": manufacturer_id},
            )
            await connection.execute(
                text(
                    "DELETE FROM priority_decisions WHERE window_id IN ("
                    "SELECT window_id FROM windows WHERE manufacturer_id = :manufacturer_id)"
                ),
                {"manufacturer_id": manufacturer_id},
            )
            await connection.execute(
                text("DELETE FROM windows WHERE manufacturer_id = :manufacturer_id"),
                {"manufacturer_id": manufacturer_id},
            )
            await connection.execute(
                text("DELETE FROM substations WHERE manufacturer_id = :manufacturer_id"),
                {"manufacturer_id": manufacturer_id},
            )
        await cleanup_engine.dispose()
        await engine.dispose()


@requires_replay_database
@pytest.mark.anyio
async def test_alert_routes_make_opening_read_only_and_manual_resolve_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib.util

    module_name = f"alert_episode_server_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, BACKEND / "server.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("server.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.chdir(BACKEND)
    monkeypatch.syspath_prepend(str(BACKEND))
    spec.loader.exec_module(module)

    async with AsyncClient(transport=ASGITransport(app=module.app), base_url="http://test") as client:
        response = await client.post(
            "/api/alerts/not-a-real-alert/resolve",
            json={"acked_by": "pytest"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "manual alert resolution is disabled"


async def _insert_priority_fixture(
    connection,
    *,
    manufacturer_id: str,
    substation_id: int,
    card_id: str,
) -> None:
    window_id = str(uuid4())
    decision_id = str(uuid4())
    substation_uid = await connection.scalar(
        text(
            "INSERT INTO substations (manufacturer_id, substation_id) "
            "VALUES (:manufacturer_id, :substation_id) "
            "ON CONFLICT (manufacturer_id, substation_id) DO UPDATE SET "
            "manufacturer_id = EXCLUDED.manufacturer_id RETURNING substation_uid"
        ),
        {"manufacturer_id": manufacturer_id, "substation_id": substation_id},
    )
    await connection.execute(
        text(
            "INSERT INTO windows (window_id, manufacturer_id, substation_id, "
            "substation_uid, window_start, window_end, source_file) "
            "VALUES (:window_id, :manufacturer_id, :substation_id, :substation_uid, "
            "now(), now(), 'pytest')"
        ),
        {
            "window_id": window_id,
            "manufacturer_id": manufacturer_id,
            "substation_id": substation_id,
            "substation_uid": substation_uid,
        },
    )
    await connection.execute(
        text(
            "INSERT INTO priority_decisions (priority_decision_id, window_id, "
            "priority_score, priority_level, priority_source, policy_version, decision_basis) "
            "VALUES (:decision_id, :window_id, 0.8, 'high', 'pytest', 'pytest', 'pytest')"
        ),
        {"decision_id": decision_id, "window_id": window_id},
    )
    await connection.execute(
        text(
            "INSERT INTO priority_cards (card_id, priority_decision_id, operational_label, "
            "primary_state, review_required, trust_level, why_reason, recommended_action) "
            "VALUES (:card_id, :decision_id, 'pytest', 'pytest', true, 'verified', "
            "'pytest', 'pytest')"
        ),
        {"card_id": card_id, "decision_id": decision_id},
    )


async def _insert_evaluation(
    connection,
    *,
    stream_key: str,
    manufacturer_id: str,
    substation_id: int,
    card_id: str,
    as_of_time: datetime,
    anomaly_label: bool,
    priority_level: str,
) -> str:
    evaluation_run_id = str(uuid4())
    result_id = str(uuid4())
    substation_uid = await connection.scalar(
        text(
            "SELECT substation_uid FROM substations "
            "WHERE manufacturer_id = :manufacturer_id AND substation_id = :substation_id"
        ),
        {"manufacturer_id": manufacturer_id, "substation_id": substation_id},
    )
    await connection.execute(
        text(
            "INSERT INTO priority_evaluation_runs (evaluation_run_id, as_of_time, "
            "stale_after_seconds, model_version, status, is_active, target_count, "
            "success_count, ranked_count, stream_key, source_kind) "
            "VALUES (:evaluation_run_id, :as_of_time, 1800, 'pytest', 'completed', false, "
            "1, 1, 1, :stream_key, 'live')"
        ),
        {
            "evaluation_run_id": evaluation_run_id,
            "as_of_time": as_of_time,
            "stream_key": stream_key,
        },
    )
    await connection.execute(
        text(
            "INSERT INTO priority_evaluation_results (evaluation_result_id, evaluation_run_id, "
            "substation_uid, manufacturer_id, substation_id, source_card_id, priority_score, "
            "priority_rank, rank_included, priority_level, risk_score, anomaly_score, "
            "anomaly_label, freshness_status, model_components) "
            "VALUES (:result_id, :evaluation_run_id, :substation_uid, :manufacturer_id, "
            ":substation_id, :card_id, 0.9, 1, true, :priority_level, 0.8, 0.95, "
            ":anomaly_label, 'fresh', '{}'::jsonb)"
        ),
        {
            "result_id": result_id,
            "evaluation_run_id": evaluation_run_id,
            "substation_uid": substation_uid,
            "manufacturer_id": manufacturer_id,
            "substation_id": substation_id,
            "card_id": card_id,
            "priority_level": priority_level,
            "anomaly_label": anomaly_label,
        },
    )
    return evaluation_run_id
