from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from collections.abc import Sequence
from typing import Any, Final
from uuid import uuid4
import asyncio
import logging

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.priority.inference import PriorityInferenceRuntime

logger = logging.getLogger(__name__)

LATEST_WINDOW_CANDIDATES_SQL: Final = """
SELECT
    s.substation_uid,
    s.manufacturer_id,
    s.substation_id,
    s.configuration_type,
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
    CAST(COALESCE(mfs.features, '{}'::jsonb) AS text) AS feature_values,
    mfs.feature_set_version
FROM substations s
LEFT JOIN LATERAL (
    SELECT selected.*
    FROM windows selected
    WHERE selected.substation_uid = s.substation_uid
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
LEFT JOIN model_feature_snapshots mfs ON mfs.window_id = w.window_id
ORDER BY s.manufacturer_id, s.substation_id
"""

INSERT_RESULT_SQL: Final = """
INSERT INTO priority_evaluation_results (
    evaluation_result_id, evaluation_run_id, substation_uid, manufacturer_id, substation_id,
    source_window_id, source_window_start, source_window_end, source_card_id,
    source_priority_decision_id, priority_score, priority_rank, rank_included,
    priority_level, risk_score, anomaly_score, anomaly_label, leadtime_bucket,
    leadtime_urgency_score, leadtime_hours, freshness_status, data_age_seconds,
    model_components
) VALUES (
    :evaluation_result_id, :evaluation_run_id, :substation_uid, :manufacturer_id, :substation_id,
    :source_window_id, :source_window_start, :source_window_end, :source_card_id,
    :source_priority_decision_id, :priority_score, :priority_rank, :rank_included,
    :priority_level, :risk_score, :anomaly_score, :anomaly_label, :leadtime_bucket,
    :leadtime_urgency_score, :leadtime_hours, :freshness_status, :data_age_seconds,
    CAST(:model_components AS jsonb)
)
"""


async def ensure_priority_evaluation_tables(engine: AsyncEngine) -> None:
    del engine


async def create_priority_evaluation(
    engine: AsyncEngine,
    *,
    as_of_time: datetime | None = None,
    stale_after_hours: int = 720,
    model_version: str = "active-priority-contract-v1",
    model_root: str | None = None,
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
    target_count = 0
    runtime_version = model_version
    try:
        runtime = PriorityInferenceRuntime(
            model_root=model_root,
            deployment_version=model_version,
        )
        runtime_version = runtime.model_version
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "SELECT pg_advisory_xact_lock("
                    "hashtext('heatgrid_priority_evaluation'))"
                )
            )
            candidate_result = await connection.execute(
                text(LATEST_WINDOW_CANDIDATES_SQL),
                {"as_of_time": as_of},
            )
            candidates = candidate_result.mappings().all()
            target_count = len(candidates)
            if expected_substations is not None and target_count != expected_substations:
                raise ValueError(
                    f"평가 대상 Substation 수가 {target_count}개입니다. "
                    f"기대값은 {expected_substations}개입니다."
                )

            await connection.execute(
                text(
                    "INSERT INTO priority_evaluation_runs ("
                    "evaluation_run_id, as_of_time, stale_after_seconds, model_version, "
                    "status, target_count"
                    ") VALUES ("
                    ":evaluation_run_id, :as_of_time, :stale_after_seconds, "
                    ":model_version, 'running', :target_count"
                    ")"
                ),
                {
                    "evaluation_run_id": evaluation_run_id,
                    "as_of_time": as_of,
                    "stale_after_seconds": stale_after_seconds,
                    "model_version": runtime_version,
                    "target_count": target_count,
                },
            )

            inference_inputs = [
                {
                    **dict(candidate),
                    "feature_values": _json_object(candidate.get("feature_values")),
                }
                for candidate in candidates
            ]
            inferences = await asyncio.to_thread(runtime.infer_batch, inference_inputs)
            rows = build_evaluation_results(
                candidates,
                inferences=inferences,
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
                    text(
                        "UPDATE priority_evaluation_runs SET is_active = false "
                        "WHERE is_active"
                    )
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
    except Exception as exc:
        try:
            await _record_failed_priority_evaluation(
                engine,
                evaluation_run_id=evaluation_run_id,
                as_of_time=as_of,
                stale_after_seconds=stale_after_seconds,
                model_version=runtime_version,
                target_count=target_count,
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception:
            logger.exception(
                "failed to persist priority evaluation failure: %s",
                evaluation_run_id,
            )
        raise
    snapshot = await get_priority_evaluation(engine, evaluation_run_id)
    if snapshot is None:
        raise RuntimeError("생성된 Priority 평가를 다시 읽을 수 없습니다.")
    return snapshot


async def _record_failed_priority_evaluation(
    engine: AsyncEngine,
    *,
    evaluation_run_id: str,
    as_of_time: datetime,
    stale_after_seconds: int,
    model_version: str,
    target_count: int,
    error: str,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO priority_evaluation_runs ("
                "evaluation_run_id, as_of_time, stale_after_seconds, model_version, "
                "status, is_active, target_count, error, completed_at"
                ") VALUES ("
                ":evaluation_run_id, :as_of_time, :stale_after_seconds, "
                ":model_version, 'failed', false, :target_count, :error, now()"
                ") ON CONFLICT (evaluation_run_id) DO UPDATE SET "
                "status = 'failed', is_active = false, target_count = :target_count, "
                "error = :error, completed_at = now()"
            ),
            {
                "evaluation_run_id": evaluation_run_id,
                "as_of_time": as_of_time,
                "stale_after_seconds": stale_after_seconds,
                "model_version": model_version,
                "target_count": target_count,
                "error": error,
            },
        )


async def ensure_latest_priority_evaluation(
    engine: AsyncEngine,
    *,
    stale_after_hours: int = 720,
    model_version: str = "active-priority-contract-v1",
    model_root: str | None = None,
    expected_substations: int | None = 31,
) -> dict[str, Any]:
    await ensure_priority_evaluation_tables(engine)
    source_time = await latest_source_time(engine)
    if source_time is None:
        raise ValueError("평가할 완료 시간 창이 없습니다.")
    latest = await get_latest_priority_evaluation(engine)
    runtime_version = PriorityInferenceRuntime(
        model_root=model_root,
        deployment_version=model_version,
    ).model_version
    if latest is not None:
        run = latest["evaluation"]
        inputs_changed = await model_inputs_changed_after(
            engine,
            _utc(run["completed_at"]),
        )
        if (
            _utc(run["as_of_time"]) >= source_time
            and int(run["stale_after_seconds"]) == stale_after_hours * 3600
            and str(run["model_version"]) == runtime_version
            and not inputs_changed
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
        model_root=model_root,
        expected_substations=expected_substations,
    )


async def latest_source_time(engine: AsyncEngine) -> datetime | None:
    async with engine.connect() as connection:
        result = await connection.execute(text("SELECT max(window_end) FROM windows"))
    value = result.scalar_one_or_none()
    return None if value is None else _utc(value)


async def model_inputs_changed_after(
    engine: AsyncEngine,
    completed_at: datetime,
) -> bool:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM model_feature_snapshots WHERE updated_at > :completed_at"
                ")"
            ),
            {"completed_at": completed_at},
        )
    return bool(result.scalar_one())


def build_evaluation_results(
    candidates: Sequence[RowMapping | dict[str, Any]],
    *,
    inferences: list[dict[str, Any]],
    evaluation_run_id: str,
    as_of_time: datetime,
    stale_after_seconds: int,
) -> list[dict[str, Any]]:
    if len(candidates) != len(inferences):
        raise ValueError("candidate and inference counts must match")
    as_of = _utc(as_of_time)
    rows: list[dict[str, Any]] = []
    for candidate, inference in zip(candidates, inferences, strict=True):
        source_window_end = candidate.get("source_window_end")
        priority_score = _float(inference.get("priority_score"))
        source_card_id = candidate.get("source_card_id")
        has_model_result = (
            candidate.get("source_window_id") is not None
            and bool(inference.get("usable"))
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

        risk_score = _float(inference.get("risk_score"))
        anomaly_score = _float(inference.get("anomaly_score"))
        leadtime_urgency = _float(inference.get("leadtime_urgency_score"))
        anomaly_label = _bool(inference.get("anomaly_label"))
        components = {
            "evaluation_source": "same_run_batch_model_inference",
            "model_version": inference.get("model_version"),
            "model_versions": inference.get("model_versions", {}),
            "inference_status": inference.get("inference_status"),
            "inference_error": inference.get("inference_error"),
            "feature_set_version": candidate.get("feature_set_version"),
            "feature_coverage": inference.get("feature_coverage", {}),
            "priority_source": inference.get("priority_source"),
            "current_best": {
                "score": _float(inference.get("current_best_priority_score")),
                "level": inference.get("current_best_priority_level"),
                "weight": 0.65,
            },
            "m1_specialist": {
                "score": _float(inference.get("m1_specialist_priority_score")),
                "level": inference.get("m1_specialist_priority_level"),
                "weight": 0.35,
                "agreement": inference.get("m1_priority_agreement"),
                **dict(inference.get("components", {}).get("m1_specialist", {})),
            },
            "risk": {
                "score": risk_score,
                "probability": _float(inference.get("risk_probability")),
                "level": inference.get("risk_level"),
            },
            "anomaly": {
                "score": anomaly_score,
                "label": anomaly_label,
            },
            "leadtime": {
                "bucket": inference.get("leadtime_bucket"),
                "urgency_score": leadtime_urgency,
                "expected_hours": _float(inference.get("leadtime_hours")),
            },
            "score_components": inference.get("components", {}).get("current_best", {}),
            "source_trace": {
                "persisted_priority_decision_id": _optional_str(
                    candidate.get("source_priority_decision_id")
                ),
                "persisted_priority_score_not_used": _float(candidate.get("priority_score")),
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
                "substation_uid": str(candidate["substation_uid"]),
                "manufacturer_id": str(candidate["manufacturer_id"]),
                "substation_id": int(candidate["substation_id"]),
                "source_window_id": _optional_str(candidate.get("source_window_id")),
                "source_window_start": candidate.get("source_window_start"),
                "source_window_end": source_window_end,
                "source_card_id": _optional_str(source_card_id),
                "source_priority_decision_id": _optional_str(
                    candidate.get("source_priority_decision_id")
                ),
                "priority_score": priority_score if has_model_result else None,
                "priority_rank": None,
                "rank_included": freshness == "fresh" and priority_score is not None,
                "priority_level": inference.get("priority_level")
                if has_model_result
                else None,
                "risk_score": risk_score if has_model_result else None,
                "anomaly_score": anomaly_score if has_model_result else None,
                "anomaly_label": anomaly_label if has_model_result else None,
                "leadtime_bucket": inference.get("leadtime_bucket")
                if has_model_result
                else None,
                "leadtime_urgency_score": leadtime_urgency
                if has_model_result
                else None,
                "leadtime_hours": _float(inference.get("leadtime_hours"))
                if has_model_result
                else None,
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
    result = _resolve_substation_result(
        latest["results"],
        substation_id=substation_id,
        manufacturer_id=manufacturer_id,
    )
    return None if result is None else {"evaluation": latest["evaluation"], "result": result}


async def get_priority_evaluation_result(
    engine: AsyncEngine,
    evaluation_run_id: str,
    substation_id: int | None = None,
    *,
    manufacturer_id: str | None = None,
    substation_uid: str | None = None,
) -> dict[str, Any] | None:
    snapshot = await get_priority_evaluation(engine, evaluation_run_id)
    if snapshot is None:
        return None
    if substation_uid is not None:
        result = next(
            (
                item
                for item in snapshot["results"]
                if str(item.get("substation_uid")) == substation_uid
            ),
            None,
        )
    elif substation_id is not None:
        result = _resolve_substation_result(
            snapshot["results"],
            substation_id=substation_id,
            manufacturer_id=manufacturer_id,
        )
    else:
        raise ValueError("substation_uid or substation_id is required")
    return None if result is None else {"evaluation": snapshot["evaluation"], "result": result}


class AmbiguousSubstationError(ValueError):
    pass


def _resolve_substation_result(
    results: list[dict[str, Any]],
    *,
    substation_id: int,
    manufacturer_id: str | None,
) -> dict[str, Any] | None:
    matches = [
        result
        for result in results
        if int(result["substation_id"]) == substation_id
        and (
            manufacturer_id is None
            or result["manufacturer_id"] == manufacturer_id
        )
    ]
    if manufacturer_id is None and len(matches) > 1:
        raise AmbiguousSubstationError(
            "manufacturer_id is required because substation_id is ambiguous"
        )
    return matches[0] if matches else None


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
        "evaluation_result_id, evaluation_run_id, substation_uid, manufacturer_id, substation_id, "
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
        "substation_uid": str(row["substation_uid"]),
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
