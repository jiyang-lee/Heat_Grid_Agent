from __future__ import annotations

from datetime import datetime
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict

from heatgrid_ops.agent.review_models import AgentRunReviewSnapshotV1


OperatorReviewStatus: TypeAlias = Literal[
    "pending",
    "approved",
    "corrected",
    "keep_human_review",
]
WorkerStatus: TypeAlias = Literal[
    "not_triggered",
    "queued",
    "running",
    "completed",
    "failed",
]
ReviewSnapshotStatus: TypeAlias = Literal[
    "pending",
    "available",
    "unavailable",
    "legacy_unavailable",
]


class FrozenApiModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AgentRunListItem(FrozenApiModel):
    run_id: str
    status: Literal["queued", "running", "completed", "failed"]
    alert_id: str
    card_id: str
    priority: str | None = None
    operator_review_status: OperatorReviewStatus
    worker_status: WorkerStatus
    review_snapshot_status: ReviewSnapshotStatus
    created_at: datetime
    updated_at: datetime


class AgentRunListPage(FrozenApiModel):
    items: tuple[AgentRunListItem, ...]
    next_cursor: str | None = None


class AgentRunReviewSnapshotResponse(FrozenApiModel):
    run_id: str
    status: ReviewSnapshotStatus
    schema_version: Literal["agent_run_review.v1"] | None = None
    snapshot_hash: str | None = None
    snapshot: AgentRunReviewSnapshotV1 | None = None
    created_at: datetime | None = None
    unavailable_reason: str | None = None
