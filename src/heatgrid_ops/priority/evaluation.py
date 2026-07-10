from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Final
from uuid import uuid4

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

PRIORITY_EVALUATION_RUNS_DDL: Final = """
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
"""

PRIORITY_EVALUATION_RESULTS_DDL: Final = """
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
"""

PRIORITY_EVALUATION_INDEX_DDL: Final = (
    "CREATE UNIQUE INDEX IF NOT EXISTS priority_evaluation_one_active_idx "
    "ON priority_evaluation_runs(is_active) WHERE is_active",
    "CREATE INDEX IF NOT EXISTS priority_evaluation_completed_idx "
    "ON priority_evaluation_runs(status, as_of_time DESC, completed_at DESC)",
    "CREATE INDEX IF NOT EXISTS priority_evaluation_result_rank_idx "
    "ON priority_evaluation_results(evaluation_run_id, rank_included, priority_rank)",
    "CREATE INDEX IF NOT EXISTS priority_evaluation_result_substation_idx "
    "ON priority_evaluation_results(manufacturer_id, substation_id, evaluation_run_id)",
)

LATEST_WINDOW_CANDIDATES_SQL: Final = """
SELECT
    s.manufacturer_id,
    s.substation_id,
    w.window_id AS source_window_id,
    w.window_start AS source_window_start,
    w.window_end AS source_window_end,
    pc.card_id AS source_card_id,
    pd.priority_decision_id AS source_priority_decision_id,
    pd.priority_score,
    pd.priority_level,
    pd.priority_source,
    pd.policy_version,
    pd.current_best_priority_score,
    pd.current_best_priority_level,
    pd.m1_specialist_priority_score,
    pd.m1_specialist_priority_level,
    pd.current_best_weight,
    pd.m1_specialist_weight,
    pd.m1_priority_agreement,
    pd.m1_specialist_primary_state,
    pd.m1_specialist_fault_group,
    pc.operational_label,
    pc.primary_state,
    pc.review_required,
    pc.trust_level,
    pc.why_reason,
    pc.recommended_action,
    pc.stable_crossing_lead_hours,
    CAST(pc.raw_card AS text) AS raw_card,
    CAST(COALESCE(features.feature_values, '{}'::jsonb) AS text) AS feature_values
FROM substations s
LEFT JOIN LATERAL (
    SELECT selected.*
    FROM windows selected
    WHERE selected.manufacturer_id = s.manufacturer_id
      AND selected.substation_id = s.substation_id
      AND selected.window_end <= :as_of_time
    ORDER BY selected.window_end DESC, selected.window_start DESC, selected.window_id DESC
    LIMIT 1
) w ON true
LEFT JOIN LATERAL (
    SELECT decision.*
    FROM priority_decisions decision
    WHERE decision.window_id = w.window_id
    ORDER BY decision.created_at DESC, decision.priority_decision_id DESC
    LIMIT 1
) pd ON true
LEFT JOIN LATERAL (
    SELECT card.*
    FROM priority_cards card
    WHERE card.priority_decision_id = pd.priority_decision_id
    ORDER BY card.created_at DESC, card.card_id DESC
    LIMIT 1
) pc ON true
LEFT JOIN LATERAL (
    SELECT jsonb_object_agg(summary.feature_name, summary.feature_value) AS feature_values
    FROM sensor_summaries summary
    WHERE summary.card_id = pc.card_id
      AND summary.feature_value IS NOT NULL
) features ON true
ORDER BY s.manufacturer_id, s.substation_id
"""

INSERT_RESULT_SQL: Final = """
INSERT INTO priority_evaluation_results (
    evaluation_result_id, evaluation_run_id, manufacturer_id, substation_id,
    source_window_id, source_window_start, source_window_end, source_card_id,
    source_priority_decision_id, priority_score, priority_rank, rank_included,
    priority_level, risk_score, anomaly_score, anomaly_label, leadtime_bucket,
    leadtime_urgency_score, leadtime_hours, freshness_status, data_age_seconds,
    model_components
) VALUES (
    :evaluation_result_id, :evaluation_run_id, :manufacturer_id, :substation_id,
    :source_window_id, :source_window_start, :source_window_end, :source_card_id,
    :source_priority_decision_id, :priority_score, :priority_rank, :rank_included,
    :priority_level, :risk_score, :anomaly_score, :anomaly_label, :leadtime_bucket,
    :leadtime_urgency_score, :leadtime_hours, :freshness_status, :data_age_seconds,
    CAST(:model_components AS jsonb)
)
"""


async def ensure_priority_evaluation_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(PRIORITY_EVALUATION_RUNS_DDL))
        await connection.execute(text(PRIORITY_EVALUATION_RESULTS_DDL))
        for statement in PRIORITY_EVALUATION_INDEX_DDL:
            await connection.execute(text(statement))


async def create_priority_evaluation(
    engine: AsyncEngine,
    *,
    as_of_time: datetime | None = None,
    stale_after_hours: int = 720,
    model_version: str = "active-priority-contract-v1",
    expected_substations: int | None = 31,
) -> dict[str, Any]:
    if stale_after_hours <= 0:
        raise ValueError("stale_after_hours는 0보다 커야 합니다.")
    await ensure_priority_evaluation_tables(engine)
    as_of = _utc(as_of_time) if as_of_time is not None else await latest_source_time(engine)
    if as_of is None:
        raise ValueError("평가할 완료 시간 창이 없습니다.")

    evaluation_run_id = str(uuid4())
    stale_after_seconds = int(stale_after_hours * 3600)
    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('heatgrid_priority_evaluation'))")
        )
        candidate_result = await connection.execute(
            text(LATEST_WINDOW_CANDIDATES_SQL),
            {"as_of_time": as_of},
        )
        candidates = candidate_result.mappings().all()
        if expected_substations is not None and len(candidates) != expected_substations:
            raise ValueError(
                f"평가 대상 Substation 수가 {len(candidates)}개입니다. "
                f"기대값은 {expected_substations}개입니다."
            )

        await connection.execute(
            text(
                "INSERT INTO priority_evaluation_runs ("
                "evaluation_run_id, as_of_time, stale_after_seconds, model_version, "
                "status, target_count"
                ") VALUES ("
                ":evaluation_run_id, :as_of_time, :stale_after_seconds, :model_version, "
                "'running', :target_count"
                ")"
            ),
            {
                "evaluation_run_id": evaluation_run_id,
                "as_of_time": as_of,
                "stale_after_seconds": stale_after_seconds,
                "model_version": model_version,
                "target_count": len(candidates),
            },
        )

        rows = build_evaluation_results(
            candidates,
            evaluation_run_id=evaluation_run_id,
            as_of_time=as_of,
            stale_after_seconds=stale_after_seconds,
        )
        if rows:
            await connection.execute(text(INSERT_RESULT_SQL), rows)

        fresh_count = sum(row["freshness_status"] == "fresh" for row in rows)
        stale_count = sum(row["freshness_status"] == "stale" for row in rows)
        missing_count = sum(row["freshness_status"] == "missing" for row in rows)
        ranked_count = sum(bool(row["rank_included"]) for row in rows)
        active_result = await connection.execute(
            text(
                "SELECT as_of_time FROM priority_evaluation_runs "
                "WHERE is_active FOR UPDATE"
            )
        )
        active_row = active_result.mappings().one_or_none()
        make_active = active_row is None or as_of >= active_row["as_of_time"]
        if make_active:
            await connection.execute(
                text("UPDATE priority_evaluation_runs SET is_active = false WHERE is_active")
            )
        await connection.execute(
            text(
                "UPDATE priority_evaluation_runs SET status = 'completed', "
                "is_active = :is_active, success_count = :success_count, "
                "stale_count = :stale_count, missing_count = :missing_count, "
                "ranked_count = :ranked_count, completed_at = now() "
                "WHERE evaluation_run_id = :evaluation_run_id"
            ),
            {
                "evaluation_run_id": evaluation_run_id,
                "is_active": make_active,
                "success_count": fresh_count,
                "stale_count": stale_count,
                "missing_count": missing_count,
                "ranked_count": ranked_count,
            },
        )
    snapshot = await get_priority_evaluation(engine, evaluation_run_id)
    if snapshot is None:
        raise RuntimeError("생성된 Priority 평가를 다시 읽을 수 없습니다.")
    return snapshot


async def ensure_latest_priority_evaluation(
    engine: AsyncEngine,
    *,
    stale_after_hours: int = 720,
    model_version: str = "active-priority-contract-v1",
    expected_substations: int | None = 31,
) -> dict[str, Any]:
    await ensure_priority_evaluation_tables(engine)
    source_time = await latest_source_time(engine)
    if source_time is None:
        raise ValueError("평가할 완료 시간 창이 없습니다.")
    latest = await get_latest_priority_evaluation(engine)
    if latest is not None:
        run = latest["evaluation"]
        if (
            _utc(run["as_of_time"]) >= source_time
            and int(run["stale_after_seconds"]) == stale_after_hours * 3600
            and str(run["model_version"]) == model_version
            and (
                expected_substations is None
                or int(run["target_count"]) == expected_substations
            )
        ):
            return latest
    return await create_priority_evaluation(
        engine,
        as_of_time=source_time,
        stale_after_hours=stale_after_hours,
        model_version=model_version,
        expected_substations=expected_substations,
    )


async def latest_source_time(engine: AsyncEngine) -> datetime | None:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT max(window_end) FROM windows"))
    value = result.scalar_one_or_none()
    return None if value is None else _utc(value)


def build_evaluation_results(
    candidates: list[RowMapping] | list[dict[str, Any]],
    *,
    evaluation_run_id: str,
    as_of_time: datetime,
    stale_after_seconds: int,
) -> list[dict[str, Any]]:
    as_of = _utc(as_of_time)
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        source_window_end = candidate.get("source_window_end")
        raw_card = _json_object(candidate.get("raw_card"))
        features = _json_object(candidate.get("feature_values"))
        priority_score = _float(candidate.get("priority_score"))
        source_card_id = candidate.get("source_card_id")
        has_model_result = (
            candidate.get("source_window_id") is not None
            and source_card_id is not None
            and priority_score is not None
        )
        age_seconds = None
        if source_window_end is not None:
            age_seconds = max(0.0, (as_of - _utc(source_window_end)).total_seconds())
        if not has_model_result:
            freshness = "missing"
        elif age_seconds is not None and age_seconds > stale_after_seconds:
            freshness = "stale"
        else:
            freshness = "fresh"

        risk_score = _first_float(
            features.get("risk_score"),
            features.get("risk_probability"),
            raw_card.get("risk_score"),
            raw_card.get("risk_probability"),
        )
        anomaly_score = _first_float(
            features.get("anomaly_policy_score"),
            features.get("anomaly_ensemble_score"),
            raw_card.get("anomaly_policy_score"),
            raw_card.get("anomaly_ensemble_score"),
        )
        leadtime_urgency = _first_float(
            features.get("leadtime_urgency_score"),
            raw_card.get("leadtime_urgency_score"),
        )
        anomaly_label = _bool(raw_card.get("anomaly_event_label"))
        components = {
            "evaluation_source": "persisted_window_model_inference",
            "priority_source": candidate.get("priority_source"),
            "policy_version": candidate.get("policy_version"),
            "current_best": {
                "score": _float(candidate.get("current_best_priority_score")),
                "level": candidate.get("current_best_priority_level"),
                "weight": _float(candidate.get("current_best_weight")),
            },
            "m1_specialist": {
                "score": _float(candidate.get("m1_specialist_priority_score")),
                "level": candidate.get("m1_specialist_priority_level"),
                "weight": _float(candidate.get("m1_specialist_weight")),
                "agreement": candidate.get("m1_priority_agreement"),
                "primary_state": candidate.get("m1_specialist_primary_state"),
                "fault_group": candidate.get("m1_specialist_fault_group"),
            },
            "risk": {
                "score": risk_score,
                "level": raw_card.get("risk_level_calibrated"),
            },
            "anomaly": {
                "score": anomaly_score,
                "label": anomaly_label,
            },
            "leadtime": {
                "bucket": raw_card.get("predicted_lead_time_bucket"),
                "urgency_score": leadtime_urgency,
                "stable_crossing_lead_hours": _float(
                    candidate.get("stable_crossing_lead_hours")
                ),
            },
            "operational": {
                "label": candidate.get("operational_label"),
                "primary_state": candidate.get("primary_state"),
                "review_required": candidate.get("review_required"),
                "trust_level": candidate.get("trust_level"),
                "why_reason": candidate.get("why_reason"),
                "recommended_action": candidate.get("recommended_action"),
            },
        }
        rows.append(
            {
                "evaluation_result_id": str(uuid4()),
                "evaluation_run_id": evaluation_run_id,
                "manufacturer_id": str(candidate["manufacturer_id"]),
                "substation_id": int(candidate["substation_id"]),
                "source_window_id": _optional_str(candidate.get("source_window_id")),
                "source_window_start": candidate.get("source_window_start"),
                "source_window_end": source_window_end,
                "source_card_id": _optional_str(source_card_id),
                "source_priority_decision_id": _optional_str(
                    candidate.get("source_priority_decision_id")
                ),
                "priority_score": priority_score,
                "priority_rank": None,
                "rank_included": freshness == "fresh" and priority_score is not None,
                "priority_level": candidate.get("priority_level")
                if has_model_result
                else None,
                "risk_score": risk_score,
                "anomaly_score": anomaly_score,
                "anomaly_label": anomaly_label,
                "leadtime_bucket": raw_card.get("predicted_lead_time_bucket"),
                "leadtime_urgency_score": leadtime_urgency,
                "leadtime_hours": _float(candidate.get("stable_crossing_lead_hours")),
                "freshness_status": freshness,
                "data_age_seconds": age_seconds,
                "model_components": _json(components),
            }
        )
    assign_priority_ranks(rows)
    return rows


def assign_priority_ranks(rows: list[dict[str, Any]]) -> None:
    ranked = [row for row in rows if row.get("rank_included")]
    ranked.sort(key=priority_sort_key)
    for rank, row in enumerate(ranked, start=1):
        row["priority_rank"] = rank


def priority_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        -_sort_number(row.get("priority_score")),
        -_sort_number(row.get("risk_score")),
        -_sort_number(row.get("leadtime_urgency_score")),
        -_sort_number(row.get("anomaly_score")),
        int(row.get("substation_id") or 0),
        str(row.get("manufacturer_id") or ""),
    )


async def get_latest_priority_evaluation(engine: AsyncEngine) -> dict[str, Any] | None:
    await ensure_priority_evaluation_tables(engine)
    query = text(
        f"SELECT {_run_columns()} FROM priority_evaluation_runs "
        "WHERE status = 'completed' "
        "ORDER BY is_active DESC, as_of_time DESC, completed_at DESC, evaluation_run_id "
        "LIMIT 1"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query)
    row = result.mappings().one_or_none()
    if row is None:
        return None
    return await get_priority_evaluation(engine, str(row["evaluation_run_id"]))


async def get_priority_evaluation(
    engine: AsyncEngine,
    evaluation_run_id: str,
) -> dict[str, Any] | None:
    await ensure_priority_evaluation_tables(engine)
    async with engine.connect() as connection:
        run_result = await connection.execute(
            text(
                f"SELECT {_run_columns()} FROM priority_evaluation_runs "
                "WHERE evaluation_run_id = :evaluation_run_id"
            ),
            {"evaluation_run_id": evaluation_run_id},
        )
        run_row = run_result.mappings().one_or_none()
        if run_row is None:
            return None
        rows_result = await connection.execute(
            text(
                f"SELECT {_result_columns()} FROM priority_evaluation_results "
                "WHERE evaluation_run_id = :evaluation_run_id "
                "ORDER BY rank_included DESC, priority_rank NULLS LAST, "
                "manufacturer_id, substation_id"
            ),
            {"evaluation_run_id": evaluation_run_id},
        )
    return {
        "evaluation": _run_from_row(run_row),
        "results": [_result_from_row(row) for row in rows_result.mappings().all()],
    }


async def get_latest_substation_result(
    engine: AsyncEngine,
    substation_id: int,
    *,
    manufacturer_id: str | None = None,
) -> dict[str, Any] | None:
    latest = await get_latest_priority_evaluation(engine)
    if latest is None:
        return None
    for result in latest["results"]:
        if int(result["substation_id"]) != substation_id:
            continue
        if manufacturer_id is not None and result["manufacturer_id"] != manufacturer_id:
            continue
        return {"evaluation": latest["evaluation"], "result": result}
    return None


async def get_priority_evaluation_result(
    engine: AsyncEngine,
    evaluation_run_id: str,
    substation_id: int,
    *,
    manufacturer_id: str | None = None,
) -> dict[str, Any] | None:
    snapshot = await get_priority_evaluation(engine, evaluation_run_id)
    if snapshot is None:
        return None
    for result in snapshot["results"]:
        if int(result["substation_id"]) != substation_id:
            continue
        if manufacturer_id is not None and result["manufacturer_id"] != manufacturer_id:
            continue
        return {"evaluation": snapshot["evaluation"], "result": result}
    return None


def latest_alert_results(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in snapshot["results"]
        if row["freshness_status"] == "fresh"
        and row["rank_included"]
        and str(row.get("priority_level") or "").lower() in {"urgent", "high"}
    ]


def _run_columns() -> str:
    return (
        "evaluation_run_id, as_of_time, stale_after_seconds, model_version, status, "
        "is_active, target_count, success_count, stale_count, missing_count, "
        "ranked_count, error, created_at, completed_at"
    )


def _result_columns() -> str:
    return (
        "evaluation_result_id, evaluation_run_id, manufacturer_id, substation_id, "
        "source_window_id, source_window_start, source_window_end, source_card_id, "
        "source_priority_decision_id, priority_score, priority_rank, rank_included, "
        "priority_level, risk_score, anomaly_score, anomaly_label, leadtime_bucket, "
        "leadtime_urgency_score, leadtime_hours, freshness_status, data_age_seconds, "
        "CAST(model_components AS text) AS model_components, created_at"
    )


def _run_from_row(row: RowMapping) -> dict[str, Any]:
    return {
        "evaluation_run_id": str(row["evaluation_run_id"]),
        "as_of_time": row["as_of_time"].isoformat(),
        "stale_after_seconds": int(row["stale_after_seconds"]),
        "model_version": str(row["model_version"]),
        "status": str(row["status"]),
        "is_active": bool(row["is_active"]),
        "target_count": int(row["target_count"]),
        "success_count": int(row["success_count"]),
        "stale_count": int(row["stale_count"]),
        "missing_count": int(row["missing_count"]),
        "ranked_count": int(row["ranked_count"]),
        "error": row["error"],
        "created_at": row["created_at"].isoformat(),
        "completed_at": _iso(row["completed_at"]),
    }


def _result_from_row(row: RowMapping) -> dict[str, Any]:
    return {
        "evaluation_result_id": str(row["evaluation_result_id"]),
        "evaluation_run_id": str(row["evaluation_run_id"]),
        "manufacturer_id": str(row["manufacturer_id"]),
        "substation_id": int(row["substation_id"]),
        "source_window_id": _optional_str(row["source_window_id"]),
        "source_window_start": _iso(row["source_window_start"]),
        "source_window_end": _iso(row["source_window_end"]),
        "source_card_id": _optional_str(row["source_card_id"]),
        "source_priority_decision_id": _optional_str(
            row["source_priority_decision_id"]
        ),
        "priority_score": _float(row["priority_score"]),
        "priority_rank": None
        if row["priority_rank"] is None
        else int(row["priority_rank"]),
        "rank_included": bool(row["rank_included"]),
        "priority_level": row["priority_level"],
        "risk_score": _float(row["risk_score"]),
        "anomaly_score": _float(row["anomaly_score"]),
        "anomaly_label": row["anomaly_label"],
        "leadtime_bucket": row["leadtime_bucket"],
        "leadtime_urgency_score": _float(row["leadtime_urgency_score"]),
        "leadtime_hours": _float(row["leadtime_hours"]),
        "freshness_status": str(row["freshness_status"]),
        "data_age_seconds": _float(row["data_age_seconds"]),
        "model_components": _json_object(row["model_components"]),
        "created_at": row["created_at"].isoformat(),
    }


def _json_object(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = orjson.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _json(value: Any) -> str:
    return orjson.dumps(value).decode("utf-8")


def _first_float(*values: Any) -> float | None:
    for value in values:
        converted = _float(value)
        if converted is not None:
            return converted
    return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sort_number(value: Any) -> float:
    converted = _float(value)
    return converted if converted is not None else float("-inf")


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
    return None


def _optional_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _utc(value: datetime | str) -> datetime:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso(value: Any) -> str | None:
    return None if value is None else value.isoformat()
