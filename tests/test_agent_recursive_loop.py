from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))

from heatgrid_ops.agent.assessment import assess_evidence, validate_output
from heatgrid_ops.agent.helpers import token_calls_from_messages
from schemas import ModelVerificationResult, OpsAgentOutput


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
    assert first.decision == "expand_internal"
    assert second.decision == "search_external"
    assert final.decision == "request_human"


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
