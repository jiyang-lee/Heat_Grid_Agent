from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, cast

import pytest

from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.models import JsonObject, OpsAgentOutput, TokenCall, TokenUsage
from heatgrid_ops.agent.run_models import AnswerQualityEvaluation, RagEvidenceSnapshot
from heatgrid_ops.agent.v2_state import AgentV2State, V2RequestState


ROOT = Path(__file__).resolve().parents[1]


class QualityRuntime:
    def __init__(self) -> None:
        self.config = AgentRuntimeConfig(
            openai_model="test-model",
            rag_top_k=5,
            agent_max_iterations=4,
            agent_evidence_threshold=0.75,
            model_score_tolerance=0.12,
            input_usd_per_1m=0.0,
            cached_input_usd_per_1m=0.0,
            output_usd_per_1m=0.0,
            pricing_source="test",
            answer_quality_enabled=True,
        )
        self.generation_profiles: list[str] = []
        self.evaluation_count = 0

    def token_usage_for(self, _source, _evidence, _card_id) -> TokenUsage:
        return TokenUsage()

    async def generate_llm_output(self, *_args, usage, **kwargs) -> OpsAgentOutput:
        self.generation_profiles.append(kwargs["execution_profile"])
        usage.calls.append(TokenCall(total_tokens=10))
        if len(self.generation_profiles) == 1:
            return OpsAgentOutput(
                summary="initial",
                action_plan="vague action",
                caution="none",
            )
        return OpsAgentOutput(
            summary="regenerated",
            action_plan="inspect the supplied evidence",
            caution="treat the cause as unconfirmed",
        )

    async def evaluate_answer_quality(self, *, usage, **_kwargs):
        self.evaluation_count += 1
        usage.calls.append(TokenCall(total_tokens=5))
        value = 2 if self.evaluation_count == 1 else 5
        return AnswerQualityEvaluation(
            correctness=value,
            completeness=value,
            actionability=value,
            evidence_grounding=value,
            calibration=value,
            unsupported_claim_risk="MEDIUM" if value == 2 else "NONE",
            failure_reasons=["insufficient evidence support"] if value == 2 else [],
            judge_confidence="HIGH",
        )


class BoundaryRuntime(QualityRuntime):
    async def evaluate_answer_quality(self, *, usage, **_kwargs):
        self.evaluation_count += 1
        usage.calls.append(TokenCall(total_tokens=5))
        value = 4
        return AnswerQualityEvaluation(
            correctness=value,
            completeness=value,
            actionability=value,
            evidence_grounding=value,
            calibration=5,
            judge_confidence="HIGH",
        )


def _quality(value: int, **updates) -> AnswerQualityEvaluation:
    return AnswerQualityEvaluation(
        correctness=value,
        completeness=value,
        actionability=value,
        evidence_grounding=value,
        calibration=value,
        judge_confidence="HIGH",
    ).model_copy(update=updates)


class SequenceRuntime(QualityRuntime):
    def __init__(
        self,
        evaluations: list[AnswerQualityEvaluation],
        *,
        fail_generation_at: int | None = None,
        fail_evaluation_at: int | None = None,
    ) -> None:
        super().__init__()
        self.evaluations = evaluations
        self.fail_generation_at = fail_generation_at
        self.fail_evaluation_at = fail_evaluation_at

    async def generate_llm_output(self, *_args, usage, **kwargs) -> OpsAgentOutput:
        self.generation_profiles.append(kwargs["execution_profile"])
        attempt = len(self.generation_profiles)
        if attempt == self.fail_generation_at:
            raise AgentDependencyError(service="llm", detail="generation unavailable")
        usage.calls.append(TokenCall(total_tokens=10))
        return OpsAgentOutput(
            summary="initial" if attempt == 1 else "regenerated",
            action_plan="inspect evidence",
            caution="keep the cause unconfirmed",
        )

    async def evaluate_answer_quality(self, *, usage, **_kwargs):
        self.evaluation_count += 1
        if self.evaluation_count == self.fail_evaluation_at:
            raise AgentDependencyError(
                service="answer_quality",
                detail="judge unavailable",
            )
        usage.calls.append(TokenCall(total_tokens=5))
        return self.evaluations[self.evaluation_count - 1]


class ExpandedFakeRag:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def search(self, request) -> RagEvidenceSnapshot:
        self.calls.append(request.top_k)
        chunks = [
            {
                "chunk_id": f"generic-{index:02d}",
                "rag_role": "domestic_inspection_standard",
                "text": "generic meter installation standard",
            }
            for index in range(1, 20)
        ]
        chunks.append(
            {
                "chunk_id": "pressure-valve-relevant",
                "rag_role": "troubleshooting_manual",
                "text": "differential pressure drop requires control valve inspection",
            }
        )
        return RagEvidenceSnapshot(
            status="available",
            retrieval=cast(
                JsonObject,
                {"backend": "pgvector", "top_k": 20, "chunks": chunks},
            ),
            references={"technical_standards": []},
        )


class RetrievalExpansionRuntime(SequenceRuntime):
    def __init__(self) -> None:
        super().__init__(
            [
                _quality(2, retrieval_insufficient=True),
                _quality(5),
            ]
        )
        self.rag: Any = ExpandedFakeRag()
        self.generation_chunk_ids: list[list[str]] = []

    async def generate_llm_output(self, *_args, usage, **kwargs) -> OpsAgentOutput:
        bundle = kwargs["snapshot_bundle"]
        retrieval = bundle.stages["rag_retrieval"].get("retrieval") or {}
        chunks = retrieval.get("chunks") or []
        self.generation_chunk_ids.append(
            [str(item.get("chunk_id")) for item in chunks if isinstance(item, dict)]
        )
        return await super().generate_llm_output(*_args, usage=usage, **kwargs)


class FailingExpandedRag:
    async def search(self, _request) -> RagEvidenceSnapshot:
        raise AgentDependencyError(service="rag", detail="expanded search unavailable")


def _state(run_id: str) -> AgentV2State:
    return AgentV2State(
        request=V2RequestState(
            run_id=run_id,
            alert_id="alert-1",
            card_id="card-1",
            source_input={"card_id": "card-1"},
            input_hash=(run_id[0] if run_id else "x") * 64,
        )
    )


@pytest.mark.anyio
async def test_initial_quality_failure_regenerates_once_and_selects_improvement() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report  # pyright: ignore[reportMissingImports]

    runtime = QualityRuntime()
    state = AgentV2State(
        request=V2RequestState(
            run_id="initial-run",
            alert_id="alert-1",
            card_id="card-1",
            source_input={"card_id": "card-1"},
            input_hash="a" * 64,
        )
    )

    envelope = await _report(runtime)(state)

    report = envelope.data["report_draft"]
    assert isinstance(report, dict)
    assert runtime.generation_profiles == [
        "report_snapshot_only",
        "report_revision_only",
    ]
    assert runtime.evaluation_count == 2
    assert report["summary"] == "regenerated"
    assert report["quality_status"] == "passed"
    assert report["score"] == 100.0
    assert report["model_call_count"] == 4
    comparison = report["answer_quality_comparison"]
    assert comparison["selected_variant"] == "regenerated"
    assert comparison["regeneration_triggered"] is True
    assert comparison["initial"]["answer"]["summary"] == "initial"
    assert comparison["regenerated"]["answer"]["summary"] == "regenerated"
    assert envelope.control.force_review is False


@pytest.mark.anyio
async def test_retrieval_failure_expands_reranks_and_regenerates_once() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report  # pyright: ignore[reportMissingImports]

    runtime = RetrievalExpansionRuntime()
    state = _state("auto-expand").model_copy(
        update={
            "request": _state("auto-expand").request.model_copy(
                update={
                    "source_input": {
                        "priority_context": {
                            "model_signals": {
                                "fault_group": (
                                    "differential pressure drop control valve"
                                )
                            }
                        }
                    }
                }
            ),
            "rag_retrieval": {
                "execution_status": "passed",
                "quality_status": "passed",
                "retrieval": {
                    "backend": "pgvector",
                    "top_k": 5,
                    "chunks": [
                        {"chunk_id": f"initial-{index}"} for index in range(5)
                    ],
                },
                "references": {"technical_standards": []},
                "retrieval_attempts": [],
            },
        }
    )

    envelope = await _report(runtime)(state)
    report = envelope.data["report_draft"]
    comparison = report["answer_quality_comparison"]
    expansion = comparison["retrieval_expansion"]

    assert runtime.rag.calls == [20]
    assert runtime.evaluation_count == 2
    assert runtime.generation_profiles == [
        "report_snapshot_only",
        "report_revision_only",
    ]
    assert runtime.generation_chunk_ids[0] == [
        "initial-0",
        "initial-1",
        "initial-2",
        "initial-3",
        "initial-4",
    ]
    assert len(runtime.generation_chunk_ids[1]) == 5
    assert "pressure-valve-relevant" in runtime.generation_chunk_ids[1]
    assert expansion["status"] == "passed"
    assert expansion["candidate_top_k"] == 20
    assert expansion["selected_count"] == 5
    assert comparison["selected_variant"] == "regenerated"
    assert report["model_call_count"] == 4


@pytest.mark.anyio
async def test_expansion_failure_regenerates_once_with_initial_evidence() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report  # pyright: ignore[reportMissingImports]

    runtime = RetrievalExpansionRuntime()
    runtime.rag = FailingExpandedRag()
    state = _state("expand-fallback").model_copy(
        update={
            "rag_retrieval": {
                "execution_status": "passed",
                "quality_status": "passed",
                "retrieval": {
                    "backend": "pgvector",
                    "top_k": 5,
                    "chunks": [
                        {"chunk_id": f"initial-{index}"} for index in range(5)
                    ],
                },
                "references": {"technical_standards": []},
                "retrieval_attempts": [],
            }
        }
    )

    envelope = await _report(runtime)(state)
    report = envelope.data["report_draft"]
    comparison = report["answer_quality_comparison"]
    expansion = comparison["retrieval_expansion"]

    assert runtime.evaluation_count == 2
    assert runtime.generation_chunk_ids[0] == runtime.generation_chunk_ids[1]
    assert expansion["status"] == "unavailable"
    assert expansion["error"] == "AgentDependencyError_unavailable"
    assert comparison["selected_variant"] == "regenerated"
    assert report["model_call_count"] == 4


@pytest.mark.anyio
async def test_passing_rag_answer_uses_one_judge_without_regeneration() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report  # pyright: ignore[reportMissingImports]

    runtime = BoundaryRuntime()
    state = AgentV2State(
        request=V2RequestState(
            run_id="boundary-run",
            alert_id="alert-1",
            card_id="card-1",
            source_input={"card_id": "card-1"},
            input_hash="b" * 64,
        )
    )

    envelope = await _report(runtime)(state)

    report = envelope.data["report_draft"]
    assert runtime.generation_profiles == ["report_snapshot_only"]
    assert runtime.evaluation_count == 1
    assert report["score"] == 82.0
    assert report["quality_status"] == "passed"
    comparison = report["answer_quality_comparison"]
    assert comparison["regeneration_triggered"] is False
    assert comparison["selected_variant"] == "initial"


@pytest.mark.anyio
async def test_both_failed_rag_answers_select_the_higher_score_for_review() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report  # pyright: ignore[reportMissingImports]

    runtime = SequenceRuntime(
        [
            _quality(3),
            _quality(3, completeness=4, actionability=4, calibration=4),
        ]
    )

    envelope = await _report(runtime)(_state("both-failed"))
    report = envelope.data["report_draft"]

    assert runtime.evaluation_count == 2
    assert report["summary"] == "regenerated"
    assert report["score"] == 69.0
    assert report["quality_status"] == "insufficient"
    assert report["answer_quality_comparison"]["selected_variant"] == "regenerated"
    assert envelope.control.force_review is True


@pytest.mark.anyio
async def test_regenerated_regression_keeps_initial_rag_answer() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report  # pyright: ignore[reportMissingImports]

    runtime = SequenceRuntime(
        [
            _quality(3, completeness=4, actionability=4, calibration=4),
            _quality(3),
        ]
    )

    envelope = await _report(runtime)(_state("regression"))
    report = envelope.data["report_draft"]

    assert report["summary"] == "initial"
    assert report["score"] == 69.0
    assert report["quality_status"] == "insufficient"
    assert report["answer_quality_comparison"]["selected_variant"] == "initial"
    assert envelope.control.force_review is True


@pytest.mark.anyio
async def test_initial_judge_failure_keeps_answer_and_requires_review() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report  # pyright: ignore[reportMissingImports]

    runtime = SequenceRuntime([_quality(5)], fail_evaluation_at=1)

    envelope = await _report(runtime)(_state("judge-failed"))
    report = envelope.data["report_draft"]
    comparison = report["answer_quality_comparison"]

    assert runtime.generation_profiles == ["report_snapshot_only"]
    assert report["summary"] == "initial"
    assert report["quality_status"] == "unavailable"
    assert comparison["regeneration_triggered"] is False
    assert comparison["evaluation_error"] == "answer_quality_unavailable"
    assert envelope.control.force_review is True


@pytest.mark.anyio
async def test_regeneration_failure_keeps_failed_initial_answer_for_review() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report  # pyright: ignore[reportMissingImports]

    runtime = SequenceRuntime([_quality(3)], fail_generation_at=2)

    envelope = await _report(runtime)(_state("regeneration-failed"))
    report = envelope.data["report_draft"]
    comparison = report["answer_quality_comparison"]

    assert runtime.generation_profiles == [
        "report_snapshot_only",
        "report_revision_only",
    ]
    assert report["summary"] == "initial"
    assert report["quality_status"] == "insufficient"
    assert comparison["regeneration_triggered"] is False
    assert comparison["evaluation_error"] == "llm_unavailable"
    assert envelope.control.force_review is True


@pytest.mark.anyio
async def test_regenerated_judge_failure_keeps_scored_initial_answer_for_review() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report  # pyright: ignore[reportMissingImports]

    runtime = SequenceRuntime([_quality(3)], fail_evaluation_at=2)

    envelope = await _report(runtime)(_state("regenerated-judge-failed"))
    report = envelope.data["report_draft"]
    comparison = report["answer_quality_comparison"]

    assert runtime.generation_profiles == [
        "report_snapshot_only",
        "report_revision_only",
    ]
    assert runtime.evaluation_count == 2
    assert report["summary"] == "initial"
    assert report["quality_status"] == "insufficient"
    assert comparison["regeneration_triggered"] is True
    assert comparison["regenerated"]["evaluation"] is None
    assert comparison["evaluation_error"] == "answer_quality_unavailable"
    assert envelope.control.force_review is True


@pytest.mark.anyio
async def test_initial_generation_failure_returns_fallback_and_unavailable_status() -> None:
    sys.path.insert(
        0,
        str(ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"),
    )
    from agent_v2_reporting import _report  # pyright: ignore[reportMissingImports]

    runtime = SequenceRuntime([], fail_generation_at=1)

    envelope = await _report(runtime)(_state("generation-failed"))
    report = envelope.data["report_draft"]

    assert runtime.evaluation_count == 0
    assert report["summary"] == "Report draft unavailable; human review is required."
    assert report["quality_status"] == "unavailable"
    assert report["answer_quality_comparison"]["selection_reason"] == (
        "initial_generation_unavailable"
    )
    assert envelope.control.force_review is True
