from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from heatgrid_ops.agent.assessment import (
    EvidenceAssessment,
    assess_evidence,
    validate_output,
)
from heatgrid_ops.agent.helpers import token_calls_from_messages
from heatgrid_ops.agent.models import ModelVerificationResult, OpsAgentOutput


def source_input(*, review_required: bool = False) -> dict:
    return {
        "priority_context": {
            "card": {"card_id": "card-1", "review_required": review_required},
            "priority": {"priority_level": "medium"},
        }
    }


def external_context(chunk_count: int) -> dict:
    return {
        "site": {"status": "mapped"},
        "weather": {"status": "available"},
        "retrieval": {
            "status": "available" if chunk_count else "no_match",
            "chunks": [
                {"chunk_id": f"chunk-{index}"} for index in range(chunk_count)
            ],
        },
    }


def verification(*, agreement: bool | None, attempt: int = 1) -> ModelVerificationResult:
    return ModelVerificationResult(
        status="verified",
        attempt=attempt,
        feature_count=313,
        feature_coverage=1.0,
        agreement=agreement,
    )


def test_model_disagreement_reruns_model_once() -> None:
    result = assess_evidence(
        source_input=source_input(),
        external_context=external_context(3),
        model_verification=verification(agreement=False),
        iteration=1,
        max_iterations=4,
        threshold=0.75,
    )

    assert result.decision == "rerun_model"


def test_internal_evidence_expansion_falls_back_to_human_review() -> None:
    first = assess_evidence(
        source_input=source_input(),
        external_context=external_context(0),
        model_verification=verification(agreement=True),
        iteration=1,
        max_iterations=4,
        threshold=0.95,
    )
    second = assess_evidence(
        source_input=source_input(),
        external_context=external_context(0),
        model_verification=verification(agreement=True),
        iteration=2,
        max_iterations=4,
        threshold=0.95,
    )

    assert first.decision == "expand_internal"
    assert second.decision == "request_human"


def test_recursive_decision_precedence_contract_is_stable() -> None:
    rerun = assess_evidence(
        source_input=source_input(),
        external_context=external_context(3),
        model_verification=verification(agreement=False),
        iteration=1,
        max_iterations=4,
        threshold=0.95,
    )
    expand = assess_evidence(
        source_input=source_input(),
        external_context=external_context(0),
        model_verification=verification(agreement=True),
        iteration=1,
        max_iterations=4,
        threshold=0.95,
    )
    human_review = assess_evidence(
        source_input=source_input(),
        external_context=external_context(0),
        model_verification=verification(agreement=True),
        iteration=2,
        max_iterations=4,
        threshold=0.95,
    )
    finalize = assess_evidence(
        source_input=source_input(),
        external_context=external_context(3),
        model_verification=verification(agreement=True),
        iteration=1,
        max_iterations=4,
        threshold=0.75,
    )

    assert [
        rerun.decision,
        expand.decision,
        human_review.decision,
        finalize.decision,
    ] == ["rerun_model", "expand_internal", "request_human", "finalize"]


def test_external_search_is_not_a_valid_loop_decision() -> None:
    with pytest.raises(ValidationError):
        EvidenceAssessment.model_validate(
            {
                "decision": "search_external",
                "confidence": 0.9,
                "evidence_score": 0.5,
                "missing_evidence": [],
                "rationale": "search the web",
            }
        )


def test_sufficient_evidence_finalizes_and_bad_output_requests_revision() -> None:
    result = assess_evidence(
        source_input=source_input(),
        external_context=external_context(3),
        model_verification=verification(agreement=True),
        iteration=1,
        max_iterations=4,
        threshold=0.75,
    )
    validation = validate_output(
        OpsAgentOutput(summary="짧음", action_plan="짧음", caution="짧음"),
        agent_mode="llm",
    )

    assert result.decision == "finalize"
    assert validation.valid is False
    assert validation.issues


def test_non_streaming_llm_messages_record_token_usage() -> None:
    calls = token_calls_from_messages(
        [
            SimpleNamespace(usage_metadata=None),
            SimpleNamespace(
                usage_metadata={
                    "input_tokens": 120,
                    "input_token_details": {"cache_read": 20},
                    "output_tokens": 30,
                    "total_tokens": 150,
                }
            ),
        ]
    )

    assert len(calls) == 1
    assert calls[0].input_tokens == 120
    assert calls[0].cached_input_tokens == 20
    assert calls[0].output_tokens == 30
    assert calls[0].total_tokens == 150
