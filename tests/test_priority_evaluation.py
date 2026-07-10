from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Final

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy import text

from heatgrid_ops.priority.evaluation import (
    assign_priority_ranks,
    create_priority_evaluation,
)

ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
SERVER_PATH: Final = BACKEND_DIR / "server.py"


def load_server(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.chdir(BACKEND_DIR)
    monkeypatch.syspath_prepend(str(BACKEND_DIR))
    spec = importlib.util.spec_from_file_location("priority_evaluation_server", SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("서버 모듈을 불러올 수 없습니다.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_priority_rank_is_deterministic_and_does_not_change_level() -> None:
    rows = [
        {
            "manufacturer_id": "manufacturer 1",
            "substation_id": 4,
            "priority_score": 90.0,
            "risk_score": 0.8,
            "leadtime_urgency_score": 0.6,
            "anomaly_score": 0.7,
            "priority_level": "low",
            "rank_included": True,
            "priority_rank": None,
        },
        {
            "manufacturer_id": "manufacturer 1",
            "substation_id": 3,
            "priority_score": 90.0,
            "risk_score": 0.8,
            "leadtime_urgency_score": 0.6,
            "anomaly_score": 0.7,
            "priority_level": "medium",
            "rank_included": True,
            "priority_rank": None,
        },
        {
            "manufacturer_id": "manufacturer 1",
            "substation_id": 2,
            "priority_score": 90.0,
            "risk_score": 0.8,
            "leadtime_urgency_score": 0.7,
            "anomaly_score": 0.2,
            "priority_level": "high",
            "rank_included": True,
            "priority_rank": None,
        },
        {
            "manufacturer_id": "manufacturer 1",
            "substation_id": 1,
            "priority_score": 90.0,
            "risk_score": 0.9,
            "leadtime_urgency_score": 0.1,
            "anomaly_score": 0.1,
            "priority_level": "low",
            "rank_included": True,
            "priority_rank": None,
        },
    ]

    assign_priority_ranks(rows)

    ordered = sorted(rows, key=lambda row: row["priority_rank"])
    assert [row["substation_id"] for row in ordered] == [1, 2, 3, 4]
    assert ordered[0]["priority_level"] == "low"


@pytest.mark.anyio
async def test_snapshot_has_31_unique_latest_windows_and_freshness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    snapshot = await create_priority_evaluation(
        module.engine,
        stale_after_hours=720,
        model_version="pytest-priority-snapshot",
        expected_substations=31,
    )
    evaluation = snapshot["evaluation"]
    results = snapshot["results"]

    async with module.engine.connect() as connection:
        latest_result = await connection.execute(
            text(
                "SELECT manufacturer_id, substation_id, max(window_end) AS window_end "
                "FROM windows WHERE window_end <= :as_of_time "
                "GROUP BY manufacturer_id, substation_id"
            ),
            {"as_of_time": datetime.fromisoformat(evaluation["as_of_time"])},
        )
    latest_by_substation = {
        (str(row["manufacturer_id"]), int(row["substation_id"])): row["window_end"].isoformat()
        for row in latest_result.mappings().all()
    }

    assert evaluation["target_count"] == 31
    assert len(results) == 31
    assert len({(row["manufacturer_id"], row["substation_id"]) for row in results}) == 31
    assert evaluation["success_count"] + evaluation["stale_count"] + evaluation["missing_count"] == 31
    for row in results:
        expected_end = latest_by_substation.get((row["manufacturer_id"], row["substation_id"]))
        assert row["source_window_end"] == expected_end
        if row["freshness_status"] != "fresh":
            assert row["rank_included"] is False
            assert row["priority_rank"] is None


@pytest.mark.anyio
async def test_historical_snapshot_records_stale_and_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    snapshot = await create_priority_evaluation(
        module.engine,
        as_of_time=datetime(2015, 3, 24, tzinfo=timezone.utc),
        stale_after_hours=1,
        model_version="pytest-historical-snapshot",
        expected_substations=31,
    )

    statuses = [row["freshness_status"] for row in snapshot["results"]]
    assert statuses.count("stale") > 0
    assert statuses.count("missing") > 0
    assert all(
        row["priority_level"] is None
        for row in snapshot["results"]
        if row["freshness_status"] == "missing"
    )


@pytest.mark.anyio
async def test_map_snapshot_and_alert_api_share_latest_evaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = load_server(monkeypatch)
    async with module.engine.begin() as connection:
        await connection.execute(text("DROP TABLE IF EXISTS agent_run_artifacts"))
        await connection.execute(text("DROP TABLE IF EXISTS agent_run_events"))
        await connection.execute(text("DROP TABLE IF EXISTS agent_runs"))
        await connection.execute(text("DROP TABLE IF EXISTS ops_alert_queue"))

    async with AsyncClient(transport=ASGITransport(app=module.app), base_url="http://test") as client:
        first_enqueue = await client.post("/api/alerts/enqueue")
        latest = await client.get("/api/priority-evaluations/latest")
        second_enqueue = await client.post("/api/alerts/enqueue")
        alerts = await client.get("/api/alerts", params={"status": "all"})
        priority_alerts = await client.get("/api/priority-evaluations/latest/alerts")
        substation = await client.get(
            f"/api/priority-evaluations/latest/substations/{latest.json()['results'][0]['substation_id']}"
        )

    evaluation_run_id = latest.json()["evaluation"]["evaluation_run_id"]
    assert latest.status_code == 200
    assert len(latest.json()["results"]) == 31
    assert first_enqueue.json()["evaluation_run_id"] == evaluation_run_id
    assert second_enqueue.json()["queued_count"] == 0
    assert second_enqueue.json()["existing_count"] == first_enqueue.json()["total_count"]
    assert all(row["evaluation_run_id"] == evaluation_run_id for row in alerts.json())
    assert all(row["evaluation_run_id"] == evaluation_run_id for row in priority_alerts.json())
    assert all(row["freshness_status"] == "fresh" for row in priority_alerts.json())
    assert len({(row["evaluation_run_id"], row["substation_id"]) for row in alerts.json()}) == len(alerts.json())
    assert substation.status_code == 200
    assert substation.json()["evaluation"]["evaluation_run_id"] == evaluation_run_id
