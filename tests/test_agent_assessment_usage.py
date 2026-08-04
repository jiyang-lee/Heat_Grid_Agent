from __future__ import annotations

import asyncio

from heatgrid_ops.agent.assessment import EvidenceAssessment
from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.contracts import EvidenceAssessmentRequest
from heatgrid_ops.agent.models import TokenCall, TokenUsage
from heatgrid_ops.agent.run_models import ChatModelAssessmentResult
from heatgrid_ops.agent.services import AgentRuntime


class AssessmentChatModel:
    async def assess(
        self,
        request: EvidenceAssessmentRequest,
    ) -> ChatModelAssessmentResult:
        return ChatModelAssessmentResult(
            assessment=EvidenceAssessment(
                decision="finalize",
                confidence=0.8,
                evidence_score=request.deterministic.evidence_score,
                rationale="model assessment",
            ),
            calls=[TokenCall(input_tokens=11, output_tokens=7, total_tokens=18)],
        )


def _runtime() -> AgentRuntime:
    return AgentRuntime(
        config=AgentRuntimeConfig(
            openai_model="test",
            rag_top_k=3,
            agent_max_iterations=4,
            agent_evidence_threshold=0.7,
            model_score_tolerance=0.1,
            input_usd_per_1m=0.0,
            cached_input_usd_per_1m=0.0,
            output_usd_per_1m=0.0,
            pricing_source="test",
        ),
        rag=object(),
        external_data=object(),
        chat_model=AssessmentChatModel(),
        model_verification=object(),
        report_writer=object(),
    )


def test_assessment_llm_calls_are_collected_for_run_usage() -> None:
    calls: list[TokenCall] = []
    assessment = asyncio.run(
        _runtime().assess_evidence(
            source_input={"priority_context": {}},
            evidence_context={},
            model_verification=None,
            iteration=1,
            max_iterations=4,
            calls=calls,
        )
    )

    assert assessment.decision in {
        "expand_internal",
        "rerun_model",
        "diagnostic_worker",
        "request_human",
        "finalize",
    }
    usage = TokenUsage(calls=calls)
    assert usage.calls == [
        TokenCall(input_tokens=11, output_tokens=7, total_tokens=18)
    ]
