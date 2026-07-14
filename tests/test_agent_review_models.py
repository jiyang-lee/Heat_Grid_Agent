from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from heatgrid_ops.agent.review_models import (
    AgentPolicyCandidate,
    AgentPolicyProposal,
    AgentRunReviewRecord,
    AgentRunReviewSnapshotV1,
    PolicyCandidateDecision,
    ReviewBudgetLineage,
    ReviewCheckpointLineage,
    ReviewDecisionStep,
    ReviewDiagnosticSnapshot,
    ReviewEvidenceSnapshot,
    ReviewFinalResultSnapshot,
    ReviewModelVerificationSnapshot,
    ReviewOpsAgentOutput,
    ReviewProvenanceSnapshot,
    ReviewSourceCardSnapshot,
    ReviewWeatherSnapshot,
)


def test_review_snapshot_rejects_extra_fields() -> None:
    payload = _snapshot().model_dump(mode="json")
    payload["unexpected"] = "not allowed"

    with pytest.raises(ValidationError):
        AgentRunReviewSnapshotV1.model_validate(payload)


def test_review_snapshot_is_frozen() -> None:
    snapshot = _snapshot()

    with pytest.raises(ValidationError):
        snapshot.run_id = "run-2"


def test_review_snapshot_nested_collections_are_immutable() -> None:
    snapshot = _snapshot()

    with pytest.raises(ValidationError):
        snapshot.decisions += (
            ReviewDecisionStep(
                sequence=2,
                decision="complete",
                reason="mutation must fail",
            ),
        )
    assert snapshot.weather is not None
    with pytest.raises(ValidationError):
        snapshot.weather.provenance.source = "mutated"


def test_review_record_and_candidate_collections_are_immutable() -> None:
    review = _review_record()
    candidate = _policy_candidate()

    with pytest.raises(ValidationError):
        review.operator_labels += ("mutated",)
    with pytest.raises(ValidationError):
        candidate.supporting_evidence_ids += ("rag-2",)


def test_immutable_tuples_preserve_json_array_serialization() -> None:
    snapshot_payload = _snapshot().model_dump(mode="json")
    candidate_payload = _policy_candidate().model_dump(mode="json")

    assert snapshot_payload["decisions"] == [
        {
            "sequence": 1,
            "decision": "run_diagnostic_worker",
            "reason": "high priority",
        }
    ]
    assert candidate_payload["supporting_evidence_ids"] == ["rag-1"]


def test_review_record_rejects_invalid_decision() -> None:
    payload = _review_record().model_dump(mode="json")
    payload["decision"] = "auto_apply"

    with pytest.raises(ValidationError):
        AgentRunReviewRecord.model_validate(payload)


def test_policy_candidate_rejects_invalid_status() -> None:
    payload = _policy_candidate().model_dump(mode="json")
    payload["status"] = "applied"

    with pytest.raises(ValidationError):
        AgentPolicyCandidate.model_validate(payload)


def test_policy_proposal_rejects_invalid_scope() -> None:
    payload = _policy_proposal().model_dump(mode="json")
    payload["scope"] = "arbitrary_code"

    with pytest.raises(ValidationError):
        AgentPolicyProposal.model_validate(payload)


def _snapshot() -> AgentRunReviewSnapshotV1:
    return AgentRunReviewSnapshotV1(
        run_id="run-1",
        result=ReviewFinalResultSnapshot(
            status="completed",
            agent_mode="fallback",
            ops_output=ReviewOpsAgentOutput(
                summary="Stable operation",
                action_plan="Continue monitoring",
                caution="Operator review required",
            ),
        ),
        decisions=(
            ReviewDecisionStep(
                sequence=1,
                decision="run_diagnostic_worker",
                reason="high priority",
            ),
        ),
        loop_count=2,
        handling_reason="diagnostic completed then human review",
        diagnostic=ReviewDiagnosticSnapshot(
            trigger="high_priority",
            status="completed",
            attempts=1,
            input_tokens=500,
            output_tokens=100,
        ),
        model_verification=ReviewModelVerificationSnapshot(
            status="verified",
            agreement=False,
            stored_score=0.4,
            current_score=0.7,
            score_delta=0.3,
            reason="score changed",
        ),
        weather=ReviewWeatherSnapshot(
            status="available",
            observed_at="2026-07-14T12:00:00+09:00",
            temperature_c=30.0,
            provenance=ReviewProvenanceSnapshot(source="weather_snapshot"),
        ),
        evidence=(
            ReviewEvidenceSnapshot(
                evidence_id="rag-1",
                document_type="operator_manual_evidence",
                source_owner="operations",
                source="manual.pdf",
                title="Operations manual",
                section="Heat exchanger",
                score=0.91,
                excerpt="Reference operating pattern.",
                provenance=ReviewProvenanceSnapshot(
                    source="manual.pdf",
                    chunk_id="chunk-1",
                ),
            ),
        ),
        source_card=ReviewSourceCardSnapshot(
            card_id="card-1",
            substation_id=31,
            manufacturer_id="manufacturer-1",
            priority_level="high",
            status="open",
            review_required=True,
            reason="temperature-flow mismatch",
        ),
        budget=ReviewBudgetLineage(
            parent_token_limit=20_000,
            parent_tokens_used=1_200,
            diagnostic_token_limit=4_000,
            diagnostic_tokens_used=600,
        ),
        checkpoint=ReviewCheckpointLineage(
            thread_id="run-1",
            namespace="",
            checkpoint_id="checkpoint-1",
            durability="sync",
        ),
    )


def _review_record() -> AgentRunReviewRecord:
    return AgentRunReviewRecord(
        review_id="review-1",
        run_id="run-1",
        review_version=1,
        idempotency_key="review-key-1",
        request_hash="a" * 64,
        decision="approve",
        reviewer="operator",
        reason="evidence verified",
        created_at=datetime.now(UTC),
    )


def _policy_proposal() -> AgentPolicyProposal:
    return AgentPolicyProposal(
        scope="evidence_threshold",
        operation="set",
        target="minimum_evidence_score",
        value=0.75,
    )


def _policy_candidate() -> AgentPolicyCandidate:
    return AgentPolicyCandidate(
        candidate_id="candidate-1",
        source_review_id="review-1",
        status="pending",
        version=1,
        proposal=AgentPolicyProposal(
            scope="human_review_route",
            operation="set",
            target="force_human_review",
            value=True,
        ),
        supporting_evidence_ids=("rag-1",),
        decision_history=(
            PolicyCandidateDecision(
                version=1,
                decision="created",
                reviewer="system",
                reason="operator correction",
                created_at=datetime.now(UTC),
            ),
        ),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
