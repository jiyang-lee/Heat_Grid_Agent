from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from agent_rerun_policy import (
    broaden_for_reason,
    target_stage_for_review,
)
from agent_review_api_models import OperatorReviewRecordResponse
from agent_rerun_repository import TargetedChildRun
from agent_stage_repository import StageName


RoutingStatus = Literal[
    "not_routable",
    "policy_candidate_created",
    "blocked_integration_disabled",
    "blocked_legacy_input_unavailable",
    "rerun_limit_reached",
    "queued",
    "scheduled",
    "schedule_failed",
]


@dataclass(frozen=True, slots=True)
class ReviewRoutingOutcome:
    review: OperatorReviewRecordResponse
    routing_status: RoutingStatus
    child_run_id: str | None = None
    target_stage: StageName | None = None
    broaden: bool = False


def routing_outcome(
    review: OperatorReviewRecordResponse,
    *,
    status: RoutingStatus | None = None,
    child: TargetedChildRun | None = None,
) -> ReviewRoutingOutcome:
    target = target_stage_for_review(review)
    if review.reason_category == "operational_policy_issue":
        resolved_status: RoutingStatus = "policy_candidate_created"
    elif status is not None:
        resolved_status = status
    elif child is not None:
        resolved_status = "queued"
    elif target is None:
        resolved_status = "not_routable"
    else:
        resolved_status = "not_routable"
    return ReviewRoutingOutcome(
        review=review,
        routing_status=resolved_status,
        child_run_id=None if child is None else child.run_id,
        target_stage=target,
        broaden=broaden_for_reason(review.reason_category),
    )
