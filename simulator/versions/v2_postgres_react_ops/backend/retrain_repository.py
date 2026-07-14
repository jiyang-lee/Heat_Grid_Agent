from __future__ import annotations

from uuid import uuid4

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from schemas import (
    ModelCandidate,
    ModelDeployment,
    ModelPromotionRequest,
    RetrainJob,
    RetrainJobActionRequest,
    RetrainJobCreateRequest,
)

async def ensure_retrain_tables(engine: AsyncEngine) -> None:
    del engine


async def create_retrain_job(
    engine: AsyncEngine,
    payload: RetrainJobCreateRequest,
) -> RetrainJob:
    await ensure_retrain_tables(engine)
    job_id = str(uuid4())
    async with engine.begin() as connection:
        feedback_ids = payload.feedback_ids
        if not feedback_ids:
            feedback_result = await connection.execute(
                text(
                    "SELECT feedback_id FROM training_feedback "
                    "ORDER BY created_at, feedback_id"
                )
            )
            feedback_ids = [str(row["feedback_id"]) for row in feedback_result.mappings()]
        snapshot_result = await connection.execute(
            text(
                "SELECT count(*) AS feedback_count, "
                "count(*) FILTER (WHERE corrected_label IS NOT NULL) AS corrected_label_count, "
                "count(*) FILTER (WHERE decision = 'approve') AS approved_count "
                "FROM training_feedback WHERE feedback_id = ANY(CAST(:feedback_ids AS uuid[]))"
            ),
            {"feedback_ids": feedback_ids},
        )
        snapshot_row = snapshot_result.mappings().one()
        snapshot = {
            "feedback_count": int(snapshot_row["feedback_count"]),
            "corrected_label_count": int(snapshot_row["corrected_label_count"]),
            "approved_count": int(snapshot_row["approved_count"]),
        }
        if snapshot["feedback_count"] == 0:
            raise ValueError("재학습에 사용할 검수 피드백이 없습니다.")
        if snapshot["corrected_label_count"] == 0:
            raise ValueError("재학습에는 하나 이상의 사람 교정 라벨이 필요합니다.")
        result = await connection.execute(
            text(
                "INSERT INTO retrain_jobs ("
                "job_id, status, requested_by, reason, feedback_ids, dataset_snapshot, "
                "auto_start_when_approved"
                ") VALUES ("
                ":job_id, 'pending_approval', :requested_by, :reason, "
                "CAST(:feedback_ids AS jsonb), CAST(:dataset_snapshot AS jsonb), "
                ":auto_start_when_approved"
                ") RETURNING " + _job_columns()
            ),
            {
                "job_id": job_id,
                "requested_by": payload.requested_by,
                "reason": payload.reason,
                "feedback_ids": _json(feedback_ids),
                "dataset_snapshot": _json(snapshot),
                "auto_start_when_approved": payload.auto_start_when_approved,
            },
        )
    return _job_from_row(result.mappings().one())


async def list_retrain_jobs(
    engine: AsyncEngine,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[RetrainJob]:
    await ensure_retrain_tables(engine)
    where = "WHERE status = :status" if status else ""
    query = text(
        f"SELECT {_job_columns()} FROM retrain_jobs {where} "
        "ORDER BY created_at DESC LIMIT :limit"
    )
    async with engine.connect() as connection:
        result = await connection.execute(
            query,
            {"status": status, "limit": max(1, min(limit, 500))},
        )
    return [_job_from_row(row) for row in result.mappings().all()]


async def get_retrain_job(engine: AsyncEngine, job_id: str) -> RetrainJob | None:
    await ensure_retrain_tables(engine)
    query = text(f"SELECT {_job_columns()} FROM retrain_jobs WHERE job_id = :job_id")
    async with engine.connect() as connection:
        result = await connection.execute(query, {"job_id": job_id})
    row = result.mappings().one_or_none()
    return None if row is None else _job_from_row(row)


async def review_retrain_job(
    engine: AsyncEngine,
    job_id: str,
    payload: RetrainJobActionRequest,
    *,
    approve: bool,
) -> RetrainJob | None:
    await ensure_retrain_tables(engine)
    status = "approved" if approve else "rejected"
    query = text(
        "UPDATE retrain_jobs SET status = :status, approved_by = :reviewer, "
        "approval_reason = :reason, approved_at = now() "
        "WHERE job_id = :job_id AND status = 'pending_approval' "
        "RETURNING " + _job_columns()
    )
    async with engine.begin() as connection:
        result = await connection.execute(
            query,
            {
                "job_id": job_id,
                "status": status,
                "reviewer": payload.reviewer,
                "reason": payload.reason,
            },
        )
    row = result.mappings().one_or_none()
    return None if row is None else _job_from_row(row)


async def mark_retrain_running(engine: AsyncEngine, job_id: str) -> None:
    await _update_job(
        engine,
        job_id,
        "status = 'running', started_at = now(), error = NULL",
        {},
    )


async def complete_retrain_job(
    engine: AsyncEngine,
    job_id: str,
    *,
    execution_metadata: dict[str, object],
    candidate_id: str,
) -> None:
    await _update_job(
        engine,
        job_id,
        "status = 'completed', execution_metadata = CAST(:metadata AS jsonb), "
        "model_candidate_id = :candidate_id, completed_at = now(), error = NULL",
        {"metadata": _json(execution_metadata), "candidate_id": candidate_id},
    )


async def fail_retrain_job(engine: AsyncEngine, job_id: str, error: str) -> None:
    await _update_job(
        engine,
        job_id,
        "status = 'failed', error = :error, completed_at = now()",
        {"error": error[:4000]},
    )


async def create_model_candidate(
    engine: AsyncEngine,
    *,
    job_id: str,
    version: str,
    artifact_uri: str,
    baseline_metrics: dict[str, object],
    candidate_metrics: dict[str, object],
    validation_summary: dict[str, object],
    candidate_id: str | None = None,
) -> ModelCandidate:
    await ensure_retrain_tables(engine)
    candidate_id = candidate_id or str(uuid4())
    query = text(
        "INSERT INTO model_candidates ("
        "candidate_id, job_id, version, artifact_uri, status, baseline_metrics, "
        "candidate_metrics, validation_summary"
        ") VALUES ("
        ":candidate_id, :job_id, :version, :artifact_uri, 'awaiting_promotion', "
        "CAST(:baseline_metrics AS jsonb), CAST(:candidate_metrics AS jsonb), "
        "CAST(:validation_summary AS jsonb)"
        ") RETURNING " + _candidate_columns()
    )
    async with engine.begin() as connection:
        result = await connection.execute(
            query,
            {
                "candidate_id": candidate_id,
                "job_id": job_id,
                "version": version,
                "artifact_uri": artifact_uri,
                "baseline_metrics": _json(baseline_metrics),
                "candidate_metrics": _json(candidate_metrics),
                "validation_summary": _json(validation_summary),
            },
        )
    return _candidate_from_row(result.mappings().one())


async def list_model_candidates(
    engine: AsyncEngine,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[ModelCandidate]:
    await ensure_retrain_tables(engine)
    where = "WHERE status = :status" if status else ""
    query = text(
        f"SELECT {_candidate_columns()} FROM model_candidates {where} "
        "ORDER BY created_at DESC LIMIT :limit"
    )
    async with engine.connect() as connection:
        result = await connection.execute(
            query,
            {"status": status, "limit": max(1, min(limit, 500))},
        )
    return [_candidate_from_row(row) for row in result.mappings().all()]


async def get_model_candidate(
    engine: AsyncEngine,
    candidate_id: str,
) -> ModelCandidate | None:
    await ensure_retrain_tables(engine)
    query = text(
        f"SELECT {_candidate_columns()} FROM model_candidates WHERE candidate_id = :candidate_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"candidate_id": candidate_id})
    row = result.mappings().one_or_none()
    return None if row is None else _candidate_from_row(row)


async def review_model_candidate(
    engine: AsyncEngine,
    candidate_id: str,
    payload: ModelPromotionRequest,
) -> tuple[ModelCandidate, ModelDeployment | None] | None:
    await ensure_retrain_tables(engine)
    candidate = await get_model_candidate(engine, candidate_id)
    if candidate is None:
        return None
    if candidate.status != "awaiting_promotion":
        raise ValueError("승격 대기 상태의 모델 후보만 처리할 수 있습니다.")
    if payload.decision == "reject":
        async with engine.begin() as connection:
            result = await connection.execute(
                text(
                    "UPDATE model_candidates SET status = 'rejected', promoted_by = :reviewer, "
                    "promotion_reason = :reason, promoted_at = now() "
                    "WHERE candidate_id = :candidate_id RETURNING " + _candidate_columns()
                ),
                {
                    "candidate_id": candidate_id,
                    "reviewer": payload.reviewer,
                    "reason": payload.reason,
                },
            )
        return _candidate_from_row(result.mappings().one()), None

    deployment_id = str(uuid4())
    async with engine.begin() as connection:
        await connection.execute(text("UPDATE model_deployments SET active = false WHERE active"))
        candidate_result = await connection.execute(
            text(
                "UPDATE model_candidates SET status = 'promoted', promoted_by = :reviewer, "
                "promotion_reason = :reason, promoted_at = now() "
                "WHERE candidate_id = :candidate_id RETURNING " + _candidate_columns()
            ),
            {
                "candidate_id": candidate_id,
                "reviewer": payload.reviewer,
                "reason": payload.reason,
            },
        )
        deployment_result = await connection.execute(
            text(
                "INSERT INTO model_deployments ("
                "deployment_id, candidate_id, version, artifact_uri, active, promoted_by"
                ") VALUES ("
                ":deployment_id, :candidate_id, :version, :artifact_uri, true, :promoted_by"
                ") RETURNING deployment_id, candidate_id, version, artifact_uri, active, "
                "promoted_by, created_at"
            ),
            {
                "deployment_id": deployment_id,
                "candidate_id": candidate_id,
                "version": candidate.version,
                "artifact_uri": candidate.artifact_uri,
                "promoted_by": payload.reviewer,
            },
        )
    return (
        _candidate_from_row(candidate_result.mappings().one()),
        _deployment_from_row(deployment_result.mappings().one()),
    )


async def get_active_model_deployment(engine: AsyncEngine) -> ModelDeployment | None:
    await ensure_retrain_tables(engine)
    query = text(
        "SELECT deployment_id, candidate_id, version, artifact_uri, active, promoted_by, "
        "created_at FROM model_deployments WHERE active ORDER BY created_at DESC LIMIT 1"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query)
    row = result.mappings().one_or_none()
    return None if row is None else _deployment_from_row(row)


async def reviewed_feedback_rows(
    engine: AsyncEngine,
    feedback_ids: list[str],
) -> list[dict[str, object]]:
    await ensure_retrain_tables(engine)
    query = text(
        "SELECT tf.feedback_id, tf.decision, tf.corrected_label, "
        "w.manufacturer_id AS manufacturer, w.substation_id, w.window_start, w.window_end "
        "FROM training_feedback tf "
        "LEFT JOIN priority_cards pc ON pc.card_id = tf.card_id "
        "LEFT JOIN priority_decisions pd ON pd.priority_decision_id = pc.priority_decision_id "
        "LEFT JOIN windows w ON w.window_id = pd.window_id "
        "WHERE tf.feedback_id = ANY(CAST(:feedback_ids AS uuid[])) "
        "ORDER BY tf.created_at, tf.feedback_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"feedback_ids": feedback_ids})
    rows: list[dict[str, object]] = []
    for row in result.mappings().all():
        rows.append(
            {
                "feedback_id": str(row["feedback_id"]),
                "decision": row["decision"],
                "corrected_label": row["corrected_label"],
                "manufacturer": row["manufacturer"],
                "substation_id": row["substation_id"],
                "window_start": None
                if row["window_start"] is None
                else row["window_start"].isoformat(),
                "window_end": None
                if row["window_end"] is None
                else row["window_end"].isoformat(),
            }
        )
    return rows


async def _update_job(
    engine: AsyncEngine,
    job_id: str,
    assignments: str,
    params: dict[str, object],
) -> None:
    await ensure_retrain_tables(engine)
    async with engine.begin() as connection:
        await connection.execute(
            text(f"UPDATE retrain_jobs SET {assignments} WHERE job_id = :job_id"),
            {"job_id": job_id, **params},
        )


def _job_columns() -> str:
    return (
        "job_id, status, requested_by, reason, CAST(feedback_ids AS text) AS feedback_ids, "
        "CAST(dataset_snapshot AS text) AS dataset_snapshot, "
        "CAST(execution_metadata AS text) AS execution_metadata, approved_by, error, "
        "model_candidate_id, created_at, approved_at, started_at, completed_at"
    )


def _candidate_columns() -> str:
    return (
        "candidate_id, job_id, version, artifact_uri, status, "
        "CAST(baseline_metrics AS text) AS baseline_metrics, "
        "CAST(candidate_metrics AS text) AS candidate_metrics, "
        "CAST(validation_summary AS text) AS validation_summary, promoted_by, "
        "promotion_reason, created_at, promoted_at"
    )


def _job_from_row(row: RowMapping) -> RetrainJob:
    return RetrainJob(
        job_id=str(row["job_id"]),
        status=str(row["status"]),
        requested_by=str(row["requested_by"]),
        reason=str(row["reason"]),
        feedback_ids=orjson.loads(row["feedback_ids"]),
        dataset_snapshot=orjson.loads(row["dataset_snapshot"]),
        execution_metadata=orjson.loads(row["execution_metadata"]),
        approved_by=row["approved_by"],
        error=row["error"],
        model_candidate_id=None
        if row["model_candidate_id"] is None
        else str(row["model_candidate_id"]),
        created_at=row["created_at"].isoformat(),
        approved_at=_iso(row["approved_at"]),
        started_at=_iso(row["started_at"]),
        completed_at=_iso(row["completed_at"]),
    )


def _candidate_from_row(row: RowMapping) -> ModelCandidate:
    return ModelCandidate(
        candidate_id=str(row["candidate_id"]),
        job_id=str(row["job_id"]),
        version=str(row["version"]),
        artifact_uri=str(row["artifact_uri"]),
        status=str(row["status"]),
        baseline_metrics=orjson.loads(row["baseline_metrics"]),
        candidate_metrics=orjson.loads(row["candidate_metrics"]),
        validation_summary=orjson.loads(row["validation_summary"]),
        promoted_by=row["promoted_by"],
        promotion_reason=row["promotion_reason"],
        created_at=row["created_at"].isoformat(),
        promoted_at=_iso(row["promoted_at"]),
    )


def _deployment_from_row(row: RowMapping) -> ModelDeployment:
    return ModelDeployment(
        deployment_id=str(row["deployment_id"]),
        candidate_id=str(row["candidate_id"]),
        version=str(row["version"]),
        artifact_uri=str(row["artifact_uri"]),
        active=bool(row["active"]),
        promoted_by=str(row["promoted_by"]),
        created_at=row["created_at"].isoformat(),
    )


def _iso(value) -> str | None:
    return None if value is None else value.isoformat()


def _json(value: object) -> str:
    return orjson.dumps(value).decode("utf-8")
