from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from agent_execution_repository import AGENT_GRAPH_TASK_KEY_V2
from agent_rerun_policy import (
    broaden_for_reason,
    rerun_block_status,
    target_stage_for_review,
)
from agent_review_api_models import OperatorReviewRecordResponse
from agent_stage_repository import StageName


@dataclass(frozen=True, slots=True)
class TargetedChildRun:
    run_id: str
    alert_id: str
    card_id: str
    target_stage: StageName
    rerun_request_id: str


async def create_targeted_child_run(
    connection: AsyncConnection,
    *,
    review: OperatorReviewRecordResponse,
    rag_quality_enabled: bool,
) -> TargetedChildRun | None:
    if review.run_id is None:
        return None
    target_stage = target_stage_for_review(review)
    if review.reason_category == "operational_policy_issue":
        target_stage = "parent_disposition"
    if target_stage is None:
        return None
    existing = await connection.execute(
        text(
            "SELECT rerun_request_id, child_run_id FROM agent_rerun_requests "
            "WHERE source_review_id = :source_review_id"
        ),
        {"source_review_id": review.review_id},
    )
    existing_row = existing.mappings().one_or_none()
    if existing_row is not None:
        return None
    source_result = await connection.execute(
        text(
            "SELECT run_id, alert_id, card_id, evaluation_run_id, substation_uid, "
            "manufacturer_id, substation_id, root_run_id, lineage_depth, "
            "CAST(source_input_snapshot AS text) AS source_input_snapshot, "
            "input_schema_version, input_hash, input_snapshot_origin, input_snapshot_status "
            "FROM agent_runs WHERE run_id = :run_id FOR UPDATE"
        ),
        {"run_id": review.run_id},
    )
    source = source_result.mappings().one()
    rerun_request_id = str(uuid4())
    idempotency_key = f"targeted-rerun:{review.review_id}"
    request_hash = sha256(
        orjson.dumps(
            {
                "source_review_id": review.review_id,
                "source_run_id": review.run_id,
                "target_stage": target_stage,
                "reason_category": review.reason_category,
                "broaden": broaden_for_reason(review.reason_category),
            },
            option=orjson.OPT_SORT_KEYS,
        )
    ).hexdigest()
    blocked_status = rerun_block_status(
        target_stage=target_stage,
        lineage_depth=int(source["lineage_depth"]),
        input_status=str(source["input_snapshot_status"]),
        rag_quality_enabled=rag_quality_enabled,
    )
    if blocked_status is not None:
        await _insert_rerun_request(
            connection,
            rerun_request_id=rerun_request_id,
            review=review,
            child_run_id=None,
            target_stage=target_stage,
            status=blocked_status,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        return None
    if review.reason_category == "operational_policy_issue":
        await _insert_rerun_request(
            connection,
            rerun_request_id=rerun_request_id,
            review=review,
            child_run_id=None,
            target_stage="parent_disposition",
            status="policy_candidate_created",
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        return None
    child_run_id = str(uuid4())
    await connection.execute(
        text(
            "INSERT INTO agent_runs ("
            "run_id, alert_id, card_id, evaluation_run_id, substation_uid, manufacturer_id, "
            "substation_id, parent_run_id, root_run_id, lineage_depth, source_review_id, "
            "target_stage, trigger_type, requested_by, trigger_reason, status, "
            "source_input_snapshot, input_schema_version, input_hash, input_snapshot_origin, "
            "input_snapshot_status"
            ") VALUES ("
            ":run_id, :alert_id, :card_id, :evaluation_run_id, :substation_uid, "
            ":manufacturer_id, :substation_id, :parent_run_id, :root_run_id, "
            ":lineage_depth, :source_review_id, :target_stage, 'targeted_rerun', "
            ":requested_by, :trigger_reason, 'queued', CAST(:source_input_snapshot AS jsonb), "
            ":input_schema_version, :input_hash, :input_snapshot_origin, 'available')"
        ),
        {
            "run_id": child_run_id,
            "alert_id": source["alert_id"],
            "card_id": source["card_id"],
            "evaluation_run_id": source["evaluation_run_id"],
            "substation_uid": source["substation_uid"],
            "manufacturer_id": source["manufacturer_id"],
            "substation_id": source["substation_id"],
            "parent_run_id": source["run_id"],
            "root_run_id": source["root_run_id"],
            "lineage_depth": int(source["lineage_depth"]) + 1,
            "source_review_id": review.review_id,
            "target_stage": target_stage,
            "requested_by": review.reviewer,
            "trigger_reason": review.reason,
            "source_input_snapshot": source["source_input_snapshot"],
            "input_schema_version": source["input_schema_version"],
            "input_hash": source["input_hash"],
            "input_snapshot_origin": source["input_snapshot_origin"],
        },
    )
    await connection.execute(
        text(
            "INSERT INTO agent_run_tasks ("
            "task_id, run_id, task_key, operation_key, checkpoint_thread_id, status, "
            "input_snapshot, input_schema_version, input_hash, input_snapshot_origin, "
            "input_snapshot_status"
            ") VALUES ("
            ":task_id, :run_id, :task_key, :operation_key, :checkpoint_thread_id, 'queued', "
            "CAST(:input_snapshot AS jsonb), :input_schema_version, :input_hash, "
            ":input_snapshot_origin, 'available')"
        ),
        {
            "task_id": str(uuid4()),
            "run_id": child_run_id,
            "task_key": AGENT_GRAPH_TASK_KEY_V2,
            "operation_key": f"agent-graph:{child_run_id}",
            "checkpoint_thread_id": child_run_id,
            "input_snapshot": source["source_input_snapshot"],
            "input_schema_version": source["input_schema_version"],
            "input_hash": source["input_hash"],
            "input_snapshot_origin": source["input_snapshot_origin"],
        },
    )
    for event_type, message in (
        ("run_queued", "targeted child run queued"),
        ("status_changed", "agent run queued"),
    ):
        await connection.execute(
            text(
                "INSERT INTO agent_run_events (run_id, event_type, message, payload) "
                "VALUES (:run_id, :event_type, :message, CAST(:payload AS jsonb))"
            ),
            {
                "run_id": child_run_id,
                "event_type": event_type,
                "message": message,
                "payload": orjson.dumps(
                    {
                        "status": "queued",
                        "parent_run_id": review.run_id,
                        "source_review_id": review.review_id,
                        "target_stage": target_stage,
                    }
                ).decode("utf-8"),
            },
        )
    await _insert_rerun_request(
        connection,
        rerun_request_id=rerun_request_id,
        review=review,
        child_run_id=child_run_id,
        target_stage=target_stage,
        status="queued",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
    )
    return TargetedChildRun(
        run_id=child_run_id,
        alert_id=str(source["alert_id"]),
        card_id=str(source["card_id"]),
        target_stage=target_stage,
        rerun_request_id=rerun_request_id,
    )


async def mark_rerun_scheduled(
    engine: AsyncEngine,
    child: TargetedChildRun,
    *,
    scheduled: bool,
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE agent_rerun_requests SET status = :status, updated_at = now() "
                "WHERE rerun_request_id = :rerun_request_id AND status = 'queued'"
            ),
            {
                "rerun_request_id": child.rerun_request_id,
                "status": "scheduled" if scheduled else "schedule_failed",
            },
        )


async def mark_child_rescheduled(engine: AsyncEngine, run_id: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE agent_rerun_requests SET status = 'scheduled', updated_at = now() "
                "WHERE child_run_id = :run_id AND status IN ('queued', 'schedule_failed')"
            ),
            {"run_id": run_id},
        )
        await connection.execute(
            text(
                "INSERT INTO agent_run_events (run_id, event_type, message, payload, operation_key) "
                "VALUES (:run_id, 'child_rescheduled', 'targeted child rescheduled', "
                "CAST(:payload AS jsonb), :operation_key) "
                "ON CONFLICT (operation_key) WHERE operation_key IS NOT NULL DO NOTHING"
            ),
            {
                "run_id": run_id,
                "payload": orjson.dumps({"status": "scheduled"}).decode("utf-8"),
                "operation_key": f"child-rescheduled:{run_id}",
            },
        )


async def _insert_rerun_request(
    connection: AsyncConnection,
    *,
    rerun_request_id: str,
    review: OperatorReviewRecordResponse,
    child_run_id: str | None,
    target_stage: StageName,
    status: str,
    idempotency_key: str,
    request_hash: str,
) -> None:
    await connection.execute(
        text(
            "INSERT INTO agent_rerun_requests ("
            "rerun_request_id, source_review_id, source_run_id, child_run_id, target_stage, "
            "status, idempotency_key, request_hash"
            ") VALUES ("
            ":rerun_request_id, :source_review_id, :source_run_id, :child_run_id, "
            ":target_stage, :status, :idempotency_key, :request_hash)"
        ),
        {
            "rerun_request_id": rerun_request_id,
            "source_review_id": review.review_id,
            "source_run_id": review.run_id,
            "child_run_id": child_run_id,
            "target_stage": target_stage,
            "status": status,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
        },
    )
