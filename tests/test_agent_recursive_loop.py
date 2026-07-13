from __future__ import annotations

from types import SimpleNamespace

import pytest

from heatgrid_ops.agent.assessment import (
    EvidenceAssessment,
    assess_evidence,
    guard_llm_assessment,
    validate_output,
)
from heatgrid_ops.agent import nodes
from heatgrid_ops.agent.external_search import (
    ExternalEvidenceSearchResult,
    _hits_from_response,
)
from heatgrid_ops.agent.helpers import token_calls_from_messages
from heatgrid_ops.agent.models import ModelVerificationResult, OpsAgentOutput
from heatgrid_ops.agent.run_models import (
    AutomationPolicySnapshot,
    ReviewTaskSnapshot,
)


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
            "chunks": [{"chunk_id": f"chunk-{index}"} for index in range(chunk_count)],
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
        external_search_enabled=True,
    )
    assert result.decision == "rerun_model"


def test_internal_then_external_evidence_routes_are_bounded() -> None:
    first = assess_evidence(
        source_input=source_input(),
        external_context=external_context(0),
        model_verification=verification(agreement=True),
        iteration=1,
        max_iterations=4,
        threshold=0.95,
        external_search_enabled=True,
    )
    second = assess_evidence(
        source_input=source_input(),
        external_context=external_context(0),
        model_verification=verification(agreement=True),
        iteration=2,
        max_iterations=4,
        threshold=0.95,
        external_search_enabled=True,
    )
    final = assess_evidence(
        source_input=source_input(),
        external_context=external_context(0),
        model_verification=verification(agreement=True),
        iteration=4,
        max_iterations=4,
        threshold=0.95,
        external_search_enabled=True,
    )
    after_external_attempt = assess_evidence(
        source_input=source_input(),
        external_context=external_context(0),
        model_verification=verification(agreement=True),
        iteration=3,
        max_iterations=4,
        threshold=0.95,
        external_search_enabled=True,
        external_search_attempted=True,
    )
    assert first.decision == "expand_internal"
    assert second.decision == "search_external"
    assert after_external_attempt.decision == "request_human"
    assert final.decision == "request_human"


def test_recursive_decision_precedence_contract_is_stable() -> None:
    # Given: the same evidence envelope at each recursive stage.
    insufficient_context = external_context(0)
    sufficient_context = external_context(3)

    # When: the deterministic assessment sees each defined loop condition.
    rerun = assess_evidence(
        source_input=source_input(),
        external_context=sufficient_context,
        model_verification=verification(agreement=False),
        iteration=1,
        max_iterations=4,
        threshold=0.95,
        external_search_enabled=True,
    )
    expand = assess_evidence(
        source_input=source_input(),
        external_context=insufficient_context,
        model_verification=verification(agreement=True),
        iteration=1,
        max_iterations=4,
        threshold=0.95,
        external_search_enabled=True,
    )
    search = assess_evidence(
        source_input=source_input(),
        external_context=insufficient_context,
        model_verification=verification(agreement=True),
        iteration=2,
        max_iterations=4,
        threshold=0.95,
        external_search_enabled=True,
    )
    human_review = assess_evidence(
        source_input=source_input(),
        external_context=insufficient_context,
        model_verification=verification(agreement=True),
        iteration=3,
        max_iterations=4,
        threshold=0.95,
        external_search_enabled=True,
        external_search_attempted=True,
    )
    finalize = assess_evidence(
        source_input=source_input(),
        external_context=sufficient_context,
        model_verification=verification(agreement=True),
        iteration=1,
        max_iterations=4,
        threshold=0.75,
        external_search_enabled=False,
    )

    # Then: PR 01 preserves the behavior that PR 02 will deliberately replace.
    assert [
        rerun.decision,
        expand.decision,
        search.decision,
        human_review.decision,
        finalize.decision,
    ] == [
        "rerun_model",
        "expand_internal",
        "search_external",
        "request_human",
        "finalize",
    ]


def test_llm_cannot_reenter_external_search_outside_policy_envelope() -> None:
    deterministic = assess_evidence(
        source_input=source_input(),
        external_context=external_context(0),
        model_verification=verification(agreement=True),
        iteration=3,
        max_iterations=4,
        threshold=0.95,
        external_search_enabled=True,
        external_search_attempted=True,
    )
    llm_candidate = EvidenceAssessment(
        decision="search_external",
        confidence=0.99,
        evidence_score=0.99,
        missing_evidence=[],
        rationale="search again",
    )

    guarded = guard_llm_assessment(
        llm_candidate,
        deterministic,
        iteration=3,
        max_iterations=4,
        external_search_enabled=True,
        model_verification=verification(agreement=True),
    )

    assert deterministic.decision == "request_human"
    assert guarded.decision == "request_human"


@pytest.mark.anyio
async def test_external_search_node_checks_policy_before_calling_provider(
) -> None:
    provider_calls = 0

    async def provider(_query: str) -> ExternalEvidenceSearchResult:
        nonlocal provider_calls
        provider_calls += 1
        return ExternalEvidenceSearchResult(status="no_match", query="query")

    async def no_event(*_args, **_kwargs) -> None:
        return None

    async def human_only_policy() -> AutomationPolicySnapshot:
        return AutomationPolicySnapshot(
            mode="human_only",
            reviewed_count=0,
            approval_rate=0,
            eligible_for_guarded_auto=False,
        )

    async def no_review_task(_task_id: str) -> None:
        return None

    async def create_action_review(_request) -> ReviewTaskSnapshot:
        return ReviewTaskSnapshot(
            task_id="review-external-1",
            task_type="external_search",
            status="pending",
        )

    runtime = SimpleNamespace(
        config=SimpleNamespace(
            external_search_budget_per_run_usd=0.02,
            external_search_estimated_cost_usd=0.01,
            external_search_allowed_domains="example.com",
            external_search_max_calls_per_run=1,
        ),
        search_external_evidence=provider,
    )
    state = {
        "run_id": "run-1",
        "alert_id": "alert-1",
        "card_id": "card-1",
        "loop_iteration": 2,
        "external_search_calls": 0,
        "external_context": {},
        "source_input": source_input(),
        "evidence_assessment": EvidenceAssessment(
            decision="search_external",
            confidence=0.8,
            evidence_score=0.5,
            missing_evidence=["reference"],
            rationale="need evidence",
        ),
    }

    result = await nodes.search_external_evidence(
        SimpleNamespace(
            runtime=runtime,
            audit=SimpleNamespace(record_event=no_event),
            reviews=SimpleNamespace(
                automation_policy=human_only_policy,
                review_task=no_review_task,
                create_review=create_action_review,
            ),
        ),
        state,
    )

    assert provider_calls == 0
    assert result["external_search_attempted"] is True
    assert result["force_review"] is True
    assert result["action_decisions"][0]["action"] == "human_review"


@pytest.mark.anyio
async def test_approved_external_search_task_resumes_controlled_action(
) -> None:
    provider_calls = 0

    async def provider(_query: str) -> ExternalEvidenceSearchResult:
        nonlocal provider_calls
        provider_calls += 1
        return ExternalEvidenceSearchResult(status="no_match", query="query")

    async def no_event(*_args, **_kwargs) -> None:
        return None

    async def human_only_policy() -> AutomationPolicySnapshot:
        return AutomationPolicySnapshot(
            mode="human_only",
            reviewed_count=0,
            approval_rate=0,
            eligible_for_guarded_auto=False,
        )

    async def approved_task(_task_id: str) -> ReviewTaskSnapshot:
        return ReviewTaskSnapshot(
            task_id="review-external-approved",
            task_type="external_search",
            status="approved",
        )

    runtime = SimpleNamespace(
        config=SimpleNamespace(
            external_search_budget_per_run_usd=0.02,
            external_search_estimated_cost_usd=0.01,
            external_search_allowed_domains="example.com",
            external_search_max_calls_per_run=1,
        ),
        search_external_evidence=provider,
    )
    state = {
        "run_id": "run-approved",
        "alert_id": "alert-approved",
        "card_id": "card-approved",
        "approved_action_task_id": "review-external-approved",
        "loop_iteration": 2,
        "external_search_calls": 0,
        "external_context": {},
        "source_input": source_input(),
        "evidence_assessment": EvidenceAssessment(
            decision="search_external",
            confidence=0.8,
            evidence_score=0.5,
            missing_evidence=["reference"],
            rationale="need evidence",
        ),
    }

    result = await nodes.search_external_evidence(
        SimpleNamespace(
            runtime=runtime,
            audit=SimpleNamespace(record_event=no_event),
            reviews=SimpleNamespace(
                automation_policy=human_only_policy,
                review_task=approved_task,
            ),
        ),
        state,
    )

    assert provider_calls == 1
    assert result["external_search_calls"] == 1
    assert result["action_decisions"][0]["action"] == "execute"


def test_external_search_rejects_sources_outside_allowed_domains() -> None:
    payload = {
        "output": [
            {
                "action": {
                    "sources": [
                        {"title": "allowed", "url": "https://docs.example.com/case"},
                        {"title": "blocked", "url": "https://example.com.evil.test/case"},
                        {"title": "blocked no url", "url": None},
                    ]
                }
            }
        ]
    }

    hits = _hits_from_response(
        payload,
        "search summary",
        5,
        allowed_domains=("example.com",),
    )
    no_citation = _hits_from_response(
        {"output": []},
        "uncited summary",
        5,
        allowed_domains=("example.com",),
    )

    assert [hit.url for hit in hits] == ["https://docs.example.com/case"]
    assert no_citation == []


def test_sufficient_evidence_finalizes_and_bad_output_requests_revision() -> None:
    result = assess_evidence(
        source_input=source_input(),
        external_context=external_context(3),
        model_verification=verification(agreement=True),
        iteration=1,
        max_iterations=4,
        threshold=0.75,
        external_search_enabled=False,
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
