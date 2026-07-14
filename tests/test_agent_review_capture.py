from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from heatgrid_ops.agent.assessment import EvidenceAssessment
from heatgrid_ops.agent.diagnostics import DiagnosticHypothesis, DiagnosticSummary
from heatgrid_ops.agent.models import ModelVerificationResult, OpsAgentOutput, TokenUsage
from heatgrid_ops.agent.review_capture import (
    build_review_capture_source,
    canonical_review_json,
    review_content_hash,
)
from heatgrid_ops.agent.review_models import (
    ReviewCaptureEvidenceSnapshot,
    ReviewEvidenceSnapshot,
    ReviewSourceCardSnapshot,
)
from heatgrid_ops.agent.run_models import AgentRunResult, RagEvidenceSnapshot
from heatgrid_ops.agent.state import (
    AgentState,
    EvidenceState,
    LoopState,
    OutputState,
    RequestState,
)


def test_capture_source_is_deterministic_when_input_mapping_order_changes() -> None:
    source_input = _source_input()
    external_context = _external_context()
    reordered_input = dict(reversed(list(deepcopy(source_input).items())))
    reordered_context = deepcopy(external_context)
    retrieval = reordered_context["retrieval"]
    assert isinstance(retrieval, dict)
    chunks = retrieval["chunks"]
    assert isinstance(chunks, list)
    retrieval["chunks"] = list(reversed(chunks))

    first = build_review_capture_source(
        _state(source_input, external_context), _result()
    )
    second = build_review_capture_source(
        _state(reordered_input, reordered_context), _result()
    )

    assert canonical_review_json(first) == canonical_review_json(second)
    assert review_content_hash(first) == review_content_hash(second)
    assert len(review_content_hash(first)) == 64


def test_capture_source_is_deterministic_when_duplicate_rank_keys_differ() -> None:
    external_context = _external_context()
    retrieval = external_context["retrieval"]
    assert isinstance(retrieval, dict)
    duplicate_a = {
        "chunk_id": "rag-tied",
        "document_type": "internal_rag",
        "source": "manual-a.pdf",
        "title": "Manual A",
        "text": "alpha reference",
        "score": 0.5,
    }
    duplicate_b = {
        "chunk_id": "rag-tied",
        "document_type": "internal_rag",
        "source": "manual-b.pdf",
        "title": "Manual B",
        "text": "beta reference",
        "score": 0.5,
    }
    retrieval["chunks"] = [duplicate_a, duplicate_b]
    reversed_context = deepcopy(external_context)
    reversed_retrieval = reversed_context["retrieval"]
    assert isinstance(reversed_retrieval, dict)
    reversed_retrieval["chunks"] = [duplicate_b, duplicate_a]

    first = build_review_capture_source(
        _state(_source_input(), external_context), _result()
    )
    second = build_review_capture_source(
        _state(_source_input(), reversed_context), _result()
    )

    assert canonical_review_json(first) == canonical_review_json(second)
    assert review_content_hash(first) == review_content_hash(second)
    assert [item.title for item in first.evidence] == ["Manual A", "Manual B"]


def test_capture_source_preserves_typed_graph_evidence_without_db_lineage() -> None:
    capture = build_review_capture_source(
        _state(_source_input(), _external_context()), _result()
    )

    assert capture.result.ops_output is not None
    assert capture.result.ops_output.summary == "Original summary"
    assert capture.handling_reason == "human verification required"
    assert capture.diagnostic.trigger == "fault_diagnosis:v1"
    assert capture.diagnostic.input_token_limit == 3_000
    assert capture.diagnostic.output_token_limit == 1_000
    assert capture.diagnostic.deadline_seconds == 60
    assert capture.diagnostic.hypotheses[0].evidence_ids == ("rag-1",)
    assert capture.model_verification is not None
    assert capture.model_verification.score_delta == pytest.approx(0.2)
    assert capture.weather is not None
    assert capture.weather.provenance.source == "weather_snapshot"
    assert [item.evidence_id for item in capture.evidence] == ["rag-1", "rag-2"]
    assert capture.source_card.reason == "temperature-flow mismatch"
    assert not hasattr(capture, "decisions")
    assert not hasattr(capture, "budget")
    assert not hasattr(capture, "checkpoint")


def test_capture_normalizes_pgstore_and_search_provenance_shape() -> None:
    rag = RagEvidenceSnapshot(
        status="available",
        retrieval={
            "status": "available",
            "source": "rag_http_server",
            "chunks": [
                {
                    "chunk_id": "manual-1",
                    "document_id": "doc-manual",
                    "document_title": "Operator note",
                    "document_type": "operator_manual_evidence",
                    "source_owner": "operations",
                    "source_file": "operator-note.md",
                    "section_title": "Inspection",
                    "score": 0.9,
                    "text": "operator observation",
                    "provenance": {
                        "backend": "pgvector",
                        "document_id": "doc-manual",
                        "chunk_id": "manual-1",
                        "document_type": "operator_manual_evidence",
                        "source_path": "evidence/operator-note.md",
                        "source_owner": "operations",
                    },
                },
                {
                    "chunk_id": "rag-1",
                    "document_id": "doc-internal",
                    "document_title": "Internal manual",
                    "document_type": "internal_rag",
                    "source_owner": "engineering",
                    "score": 0.8,
                    "text": "internal reference",
                    "provenance": {
                        "backend": "jsonl",
                        "document_id": "doc-internal",
                        "chunk_id": "rag-1",
                        "document_type": "internal_rag",
                        "source_path": "rag/internal-manual.md",
                        "source_owner": "engineering",
                    },
                },
                {
                    "chunk_id": "rag-no-source",
                    "document_title": "Unlocated reference",
                    "document_type": "internal_rag",
                    "score": 0.7,
                    "text": "source location unavailable",
                    "provenance": {"backend": "jsonl"},
                },
            ],
        },
        references={},
    )
    external_context = _external_context()
    external_context["retrieval"] = rag.retrieval

    capture = build_review_capture_source(
        _state(_source_input(), external_context), _result()
    )
    evidence = {item.evidence_id: item for item in capture.evidence}

    manual = evidence["manual-1"]
    internal = evidence["rag-1"]
    assert manual.document_type == "operator_manual_evidence"
    assert manual.source_owner == "operations"
    assert manual.provenance is not None
    assert manual.provenance.source == "evidence/operator-note.md"
    assert manual.provenance.document_id == "doc-manual"
    assert manual.provenance.chunk_id == "manual-1"
    assert internal.document_type == "internal_rag"
    assert internal.source == "rag/internal-manual.md"
    assert internal.provenance is not None
    assert internal.provenance.source == "rag/internal-manual.md"
    assert internal.provenance.source_owner == "engineering"
    assert "rag-no-source" not in evidence


def test_capture_source_rejects_mutation_and_unknown_fields() -> None:
    capture = build_review_capture_source(
        _state(_source_input(), _external_context()), _result()
    )

    with pytest.raises(Exception):  # noqa: B017
        capture.loop_count = 99
    with pytest.raises(Exception):  # noqa: B017
        type(capture).model_validate({**capture.model_dump(), "url": "https://x"})


def test_capture_source_rejects_a_result_from_another_run() -> None:
    result = _result().model_copy(update={"run_id": "run-other"})

    with pytest.raises(RuntimeError, match="run_id"):
        build_review_capture_source(
            _state(_source_input(), _external_context()), result
        )


def test_persisted_snapshot_keeps_lineage_fields_required() -> None:
    evidence_schema = ReviewEvidenceSnapshot.model_json_schema()
    card_schema = ReviewSourceCardSnapshot.model_json_schema()

    assert "provenance" in evidence_schema["required"]
    assert "priority_level" in card_schema["required"]
    assert "reason" in card_schema["required"]
    with pytest.raises(ValidationError):
        ReviewEvidenceSnapshot.model_validate(
            {
                "evidence_id": "rag-1",
                "document_type": "internal_rag",
                "source": "manual.pdf",
                "title": "Manual",
                "score": 0.9,
                "excerpt": "reference",
            }
        )
    with pytest.raises(ValidationError):
        ReviewSourceCardSnapshot.model_validate(
            {"card_id": "card-1", "review_required": True}
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_capture_models_reject_non_finite_scores(value: float) -> None:
    with pytest.raises(ValidationError):
        ReviewCaptureEvidenceSnapshot(
            evidence_id="rag-1",
            document_type="internal_rag",
            source="manual.pdf",
            title="Manual",
            score=value,
            excerpt="reference",
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_capture_omits_non_finite_optional_numbers(value: float) -> None:
    external_context = _external_context()
    retrieval = external_context["retrieval"]
    weather = external_context["weather"]
    assert isinstance(retrieval, dict)
    assert isinstance(weather, dict)
    chunks = retrieval["chunks"]
    assert isinstance(chunks, list)
    first_chunk = chunks[0]
    assert isinstance(first_chunk, dict)
    first_chunk["score"] = value
    weather["temperature_c"] = value
    state = _state(_source_input(), external_context)
    verification = state.evidence.model_verification
    assert verification is not None
    state = state.model_copy(
        update={
            "evidence": state.evidence.model_copy(
                update={
                    "model_verification": verification.model_copy(
                        update={"priority_score": value}
                    )
                }
            )
        }
    )

    capture = build_review_capture_source(state, _result())

    assert all(item.evidence_id != "rag-2" for item in capture.evidence)
    assert capture.weather is not None
    assert capture.weather.temperature_c is None
    assert capture.model_verification is not None
    assert capture.model_verification.current_score is None
    assert "NaN" not in canonical_review_json(capture)
    assert "Infinity" not in canonical_review_json(capture)


def _state(source_input: dict, external_context: dict) -> AgentState:
    return AgentState(
        request=RequestState(
            run_id="run-1",
            alert_id="alert-1",
            card_id="card-1",
            source_input=source_input,
        ),
        evidence=EvidenceState(
            external_context=external_context,
            model_verification=ModelVerificationResult(
                status="verified",
                agreement=False,
                component_agreement={"risk": False, "anomaly": True},
                stored_priority_score=0.5,
                priority_score=0.7,
                priority_score_delta=0.2,
                reasons=["score changed"],
            ),
            diagnostic_summary=DiagnosticSummary(
                status="completed",
                hypotheses=[
                    DiagnosticHypothesis(
                        hypothesis_id="hypothesis-1",
                        title="Heat exchanger restriction",
                        rationale="The pattern matches the cited manual.",
                        evidence_ids=["rag-1"],
                        confidence=0.8,
                    )
                ],
                attempts=1,
                input_tokens=500,
                output_tokens=80,
            ),
        ),
        loop=LoopState(
            assessment=EvidenceAssessment(
                decision="request_human",
                confidence=0.8,
                evidence_score=0.7,
                rationale="human verification required",
            ),
            iteration=3,
            diagnostic_attempted=True,
        ),
        output=OutputState(
            value=OpsAgentOutput(
                summary="Original summary",
                action_plan="Original action plan",
                caution="Original caution",
            ),
            token_usage=TokenUsage(total_tokens=900),
            mode="fallback",
        ),
    )


def _source_input() -> dict:
    return {
        "card_id": "card-1",
        "sections": {},
        "priority_context": {
            "card": {"status": "open", "review_required": True},
            "priority": {"priority_level": "urgent"},
            "explanation": {"why_reason": "temperature-flow mismatch"},
        },
        "raw_context": {
            "window": {"substation_id": 31, "manufacturer_id": "maker-1"}
        },
    }


def _external_context() -> dict:
    return {
        "weather": {
            "status": "available",
            "temperature_c": -2.0,
            "humidity_percent": 54.0,
            "provenance": {"source": "weather_snapshot", "snapshot_id": "wx-1"},
        },
        "retrieval": {
            "chunks": [
                {
                    "chunk_id": "rag-2",
                    "document_type": "internal_rag",
                    "source": "manual-b.pdf",
                    "title": "Manual B",
                    "text": "second reference",
                    "score": 0.8,
                },
                {
                    "chunk_id": "rag-1",
                    "document_type": "operator_manual_evidence",
                    "source_owner": "operations",
                    "source": "manual-a.pdf",
                    "title": "Manual A",
                    "section": "Inspection",
                    "text": "first reference",
                    "score": 0.9,
                },
            ]
        },
    }


def _result() -> AgentRunResult:
    return AgentRunResult(
        run_id="run-1",
        status="completed",
        input_source="alert",
        alert_id="alert-1",
        card_id="card-1",
        agent_mode="fallback",
        ops_output=OpsAgentOutput(
            summary="Original summary",
            action_plan="Original action plan",
            caution="Original caution",
        ),
        token_usage=TokenUsage(total_tokens=900),
    )
