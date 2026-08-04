from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from agent_review_snapshot_repository import (
    SnapshotStoreResult,
    SnapshotWrite,
    record_review_snapshot_pending,
    record_review_snapshot_unavailable,
    store_review_snapshot,
)
from heatgrid_ops.agent.review_capture import canonical_review_json, review_content_hash
from heatgrid_ops.agent.review_models import AgentRunReviewSnapshotV1


@dataclass(frozen=True, slots=True)
class PostgresReviewSnapshotAdapter:
    engine: AsyncEngine

    async def capture(
        self,
        snapshot: AgentRunReviewSnapshotV1,
    ) -> SnapshotStoreResult:
        canonical = canonical_review_json(snapshot).encode("utf-8")
        return await store_review_snapshot(
            self.engine,
            SnapshotWrite(
                run_id=snapshot.run_id,
                schema_version=snapshot.schema_version,
                snapshot_hash=review_content_hash(snapshot),
                canonical_snapshot=canonical,
            ),
        )

    async def mark_unavailable(self, run_id: str, reason: str) -> None:
        await record_review_snapshot_unavailable(
            self.engine,
            run_id=run_id,
            reason=reason,
        )

    async def mark_pending(self, run_id: str) -> None:
        await record_review_snapshot_pending(self.engine, run_id=run_id)
