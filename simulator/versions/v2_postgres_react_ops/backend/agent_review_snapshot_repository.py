from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_review_api_models import AgentRunReviewSnapshotResponse
from agent_run_event_repository import AgentRunEventRecord, insert_agent_run_event
from heatgrid_ops.agent.review_models import AgentRunReviewSnapshotV1


@dataclass(frozen=True, slots=True)
class SnapshotWrite:
    run_id: str
    schema_version: Literal["agent_run_review.v1"]
    snapshot_hash: str
    canonical_snapshot: bytes


@dataclass(frozen=True, slots=True)
class SnapshotStoreResult:
    status: Literal["inserted", "existing", "conflict"]
    snapshot_hash: str


async def store_review_snapshot(
    engine: AsyncEngine,
    write: SnapshotWrite,
) -> SnapshotStoreResult:
    async with engine.begin() as connection:
        inserted = await connection.execute(
            text(
                "INSERT INTO agent_run_review_snapshots ("
                "run_id, schema_version, snapshot_hash, snapshot"
                ") VALUES ("
                ":run_id, :schema_version, :snapshot_hash, CAST(:snapshot AS jsonb)"
                ") ON CONFLICT (run_id) DO NOTHING RETURNING snapshot_hash"
            ),
            {
                "run_id": write.run_id,
                "schema_version": write.schema_version,
                "snapshot_hash": write.snapshot_hash,
                "snapshot": write.canonical_snapshot.decode("utf-8"),
            },
        )
        inserted_hash = inserted.scalar_one_or_none()
        if inserted_hash is not None:
            return SnapshotStoreResult(status="inserted", snapshot_hash=str(inserted_hash))

        existing = await connection.execute(
            text(
                "SELECT snapshot_hash FROM agent_run_review_snapshots "
                "WHERE run_id = :run_id"
            ),
            {"run_id": write.run_id},
        )
        existing_hash = str(existing.scalar_one())
        if existing_hash == write.snapshot_hash:
            return SnapshotStoreResult(status="existing", snapshot_hash=existing_hash)

        await insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=write.run_id,
                event_type="review_snapshot_conflict",
                message="review snapshot hash conflict; original preserved",
                payload={
                    "existing_hash": existing_hash,
                    "rejected_hash": write.snapshot_hash,
                },
                operation_key=(
                    f"review-snapshot-conflict:{write.run_id}:{write.snapshot_hash}"
                ),
            ),
        )
        return SnapshotStoreResult(status="conflict", snapshot_hash=existing_hash)


async def record_review_snapshot_unavailable(
    engine: AsyncEngine,
    *,
    run_id: str,
    reason: str,
) -> None:
    async with engine.begin() as connection:
        await insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=run_id,
                event_type="review_snapshot_unavailable",
                message="review snapshot capture unavailable",
                payload={"reason": reason[:1000]},
                operation_key=f"review-snapshot-unavailable:{run_id}",
            ),
        )


async def record_review_snapshot_pending(
    engine: AsyncEngine,
    *,
    run_id: str,
) -> None:
    async with engine.begin() as connection:
        await insert_agent_run_event(
            connection,
            AgentRunEventRecord(
                run_id=run_id,
                event_type="review_snapshot_pending",
                message="review snapshot capture pending",
                payload={},
                operation_key=f"review-snapshot-pending:{run_id}",
            ),
        )


async def get_review_snapshot(
    engine: AsyncEngine,
    run_id: str,
) -> AgentRunReviewSnapshotResponse | None:
    query = text(
        "SELECT runs.run_id, runs.status AS run_status, snapshot.schema_version, "
        "snapshot.snapshot_hash, CAST(snapshot.snapshot AS text) AS snapshot, "
        "snapshot.created_at, unavailable.payload ->> 'reason' AS unavailable_reason, "
        "runs.review_snapshot_expected "
        "FROM agent_runs runs "
        "LEFT JOIN agent_run_review_snapshots snapshot ON snapshot.run_id = runs.run_id "
        "LEFT JOIN LATERAL ("
        "SELECT events.payload FROM agent_run_events events "
        "WHERE events.run_id = runs.run_id "
        "AND events.event_type = 'review_snapshot_unavailable' "
        "ORDER BY events.event_id DESC LIMIT 1"
        ") unavailable ON TRUE "
        "WHERE runs.run_id = :run_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"run_id": run_id})
    row = result.mappings().one_or_none()
    if row is None:
        return None
    if row["snapshot"] is not None:
        return AgentRunReviewSnapshotResponse(
            run_id=str(row["run_id"]),
            status="available",
            schema_version=row["schema_version"],
            snapshot_hash=row["snapshot_hash"],
            snapshot=AgentRunReviewSnapshotV1.model_validate(
                orjson.loads(row["snapshot"])
            ),
            created_at=row["created_at"],
        )
    if row["unavailable_reason"] is not None:
        return AgentRunReviewSnapshotResponse(
            run_id=str(row["run_id"]),
            status="unavailable",
            unavailable_reason=str(row["unavailable_reason"]),
        )
    if str(row["run_status"]) in {"queued", "running"}:
        return AgentRunReviewSnapshotResponse(
            run_id=str(row["run_id"]),
            status="pending",
        )
    if row["review_snapshot_expected"] is True:
        return AgentRunReviewSnapshotResponse(
            run_id=str(row["run_id"]),
            status="unavailable",
            unavailable_reason="review_snapshot_missing_after_terminal_run",
        )
    return AgentRunReviewSnapshotResponse(
        run_id=str(row["run_id"]),
        status="legacy_unavailable",
    )
