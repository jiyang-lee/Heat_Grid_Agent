from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(
    0,
    str(Path(__file__).parents[1] / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
)

from agent_review_api_models import OperatorReviewRecordResponse, OperatorReviewSubmitRequest
from agent_rerun_policy import TARGET_STAGE_BY_REASON, target_stage_for_review


def _review(reason_category: str | None) -> OperatorReviewRecordResponse:
    return OperatorReviewRecordResponse(
        review_id="review-1",
        review_task_id="task-1",
        run_id="run-1",
        subject_type="agent_run",
        subject_key="run-1",
        review_contract_version=2,
        review_version=1,
        idempotency_key="key-1",
        request_hash="a" * 64,
        decision="keep_human_review",
        reviewer="operator",
        reason="needs review",
        reason_category=reason_category,
        created_at=datetime.now(UTC),
    )


def test_all_canonical_reason_categories_route_to_expected_stage() -> None:
    expected = {
        "ml_prediction_issue": "ml_validation",
        "weather_context_issue": "weather_context",
        "rag_retrieval_issue": "rag_retrieval",
        "rag_interpretation_issue": "rag_interpretation",
        "fault_analysis_issue": "fault_analysis",
        "escalation_issue": "higher_model_reassessment",
        "report_draft_issue": "report_draft",
        "insufficient_evidence": "rag_retrieval",
        "operational_policy_issue": None,
    }

    assert set(TARGET_STAGE_BY_REASON) == set(expected) - {"operational_policy_issue"}
    for reason, target in expected.items():
        assert target_stage_for_review(_review(reason)) == target


def test_canonical_review_rejects_historical_reason_name() -> None:
    with pytest.raises(ValidationError):
        OperatorReviewSubmitRequest(
            expected_review_version=0,
            idempotency_key="key-1",
            decision="keep_human_review",
            reviewer="operator",
            reason="needs review",
            reason_category="legacy_reject",
            disposition="urgent_review",
        )
