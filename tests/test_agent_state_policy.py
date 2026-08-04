from __future__ import annotations

from inspect import signature

import pytest
from pydantic import ValidationError

from heatgrid_ops.agent.decision_policy import (
    DecisionContext,
    default_decision_policy,
)
from heatgrid_ops.agent.contracts import AgentRunRequest
from heatgrid_ops.agent.models import ModelVerificationResult
from heatgrid_ops.agent.state import AgentState, RequestState


def test_state_contract_is_nested_and_frozen() -> None:
    state = AgentState(
        request=RequestState(
            run_id="run-1",
            alert_id="alert-1",
            card_id="card-1",
        )
    )

    assert set(state.model_dump()) == {
        "request",
        "evidence",
        "loop",
        "output",
        "audit",
        "result",
    }
    with pytest.raises(ValidationError):
        setattr(state.request, "card_id", "card-2")


def test_decision_policy_priority_is_stable() -> None:
    policy = default_decision_policy()

    assert policy.priority == (
        "rerun_model",
        "expand_internal",
        "diagnostic_worker",
        "request_human",
        "finalize",
    )


def test_model_revalidation_precedes_internal_rag() -> None:
    policy = default_decision_policy()
    decision = policy.decide(
        DecisionContext(
            model_verification=ModelVerificationResult(
                status="verified",
                attempt=1,
                agreement=False,
            ),
            rag_chunk_count=0,
            review_required=True,
            evidence_score=0.2,
            evidence_threshold=0.75,
            iteration=1,
            max_iterations=4,
            diagnostic_available=True,
        )
    )

    assert decision == "rerun_model"


def test_high_priority_selects_diagnostic_worker_when_available() -> None:
    decision = default_decision_policy().decide(
        DecisionContext(
            model_verification=ModelVerificationResult(
                status="verified",
                attempt=2,
                agreement=True,
            ),
            rag_chunk_count=2,
            review_required=False,
            evidence_score=0.9,
            evidence_threshold=0.75,
            iteration=1,
            max_iterations=4,
            diagnostic_available=True,
            priority_level="high",
        )
    )

    assert decision == "diagnostic_worker"


def test_human_review_follows_diagnostic_worker_without_reselection() -> None:
    decision = default_decision_policy().decide(
        DecisionContext(
            model_verification=ModelVerificationResult(
                status="verified",
                attempt=2,
                agreement=True,
            ),
            rag_chunk_count=2,
            review_required=True,
            evidence_score=0.9,
            evidence_threshold=0.75,
            iteration=1,
            max_iterations=4,
            diagnostic_available=False,
            priority_level="high",
        )
    )

    assert decision == "request_human"


def test_agent_request_has_no_external_search_resume_input() -> None:
    assert "approved_action_task_id" not in signature(AgentRunRequest).parameters
