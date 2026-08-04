from __future__ import annotations

from typing import Final

from agent_review_api_models import OperatorReviewRecordResponse
from heatgrid_ops.agent.v2_models import StageName


TARGET_STAGE_BY_REASON: Final[dict[str, StageName]] = {
    "ml_prediction_issue": "ml_validation",
    "weather_context_issue": "weather_context",
    "rag_retrieval_issue": "rag_retrieval",
    "rag_interpretation_issue": "rag_interpretation",
    "fault_analysis_issue": "fault_analysis",
    "escalation_issue": "higher_model_reassessment",
    "report_draft_issue": "report_draft",
    "insufficient_evidence": "rag_retrieval",
}

CANONICAL_REASON_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "ml_prediction_issue",
        "weather_context_issue",
        "rag_retrieval_issue",
        "rag_interpretation_issue",
        "fault_analysis_issue",
        "escalation_issue",
        "report_draft_issue",
        "insufficient_evidence",
        "operational_policy_issue",
    }
)


def target_stage_for_review(review: OperatorReviewRecordResponse) -> StageName | None:
    if review.reason_category in TARGET_STAGE_BY_REASON:
        return TARGET_STAGE_BY_REASON[review.reason_category]
    return None


def is_canonical_reason_category(value: str | None) -> bool:
    return value in CANONICAL_REASON_CATEGORIES


def broaden_for_reason(value: str | None) -> bool:
    return value == "insufficient_evidence"


def rerun_block_status(
    *,
    target_stage: StageName,
    lineage_depth: int,
    input_status: str,
    rag_quality_enabled: bool,
) -> str | None:
    if lineage_depth >= 2:
        return "rerun_limit_reached"
    if input_status != "available":
        return "blocked_legacy_input_unavailable"
    if target_stage in {"rag_retrieval", "rag_interpretation"} and not rag_quality_enabled:
        return "blocked_integration_disabled"
    return None
