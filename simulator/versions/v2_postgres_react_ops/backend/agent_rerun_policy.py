from __future__ import annotations

from typing import Final

from agent_review_api_models import OperatorReviewRecordResponse
from agent_stage_repository import StageName


TARGET_STAGE_BY_REASON: Final[dict[str, StageName]] = {
    "model_disagreement": "ml_validation",
    "ml_disagreement": "ml_validation",
    "rag_quality": "rag_retrieval",
    "rag_evidence_insufficient": "rag_retrieval",
    "fault_analysis": "fault_analysis",
    "fault_analysis_insufficient": "fault_analysis",
    "higher_model_reassessment": "higher_model_reassessment",
    "report_quality": "report_fidelity",
    "report_fidelity": "report_fidelity",
}


def target_stage_for_review(review: OperatorReviewRecordResponse) -> StageName | None:
    if review.reason_category in TARGET_STAGE_BY_REASON:
        return TARGET_STAGE_BY_REASON[str(review.reason_category)]
    return None


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
