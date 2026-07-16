from __future__ import annotations

import asyncio

from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.models import OpsAgentOutput
from heatgrid_ops.agent.run_models import ChatModelResult
from heatgrid_ops.agent.services import AgentRuntime


class RecordingChatModel:
    def __init__(self) -> None:
        self.requests = []

    async def generate(self, request):
        self.requests.append(request)
        return ChatModelResult(
            output=OpsAgentOutput(
                summary="summary",
                action_plan="action plan",
                caution="caution",
            )
        )


def test_work_order_generation_uses_the_dedicated_model() -> None:
    integrated_model = RecordingChatModel()
    work_order_model = RecordingChatModel()
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(
            openai_model="gpt-5.4-mini",
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
        chat_model=integrated_model,
        work_order_model=work_order_model,
        model_verification=object(),
        report_writer=object(),
    )

    asyncio.run(
        runtime.generate_llm_output(
            source_input={},
            evidence_context={},
            card_id="card-1",
        )
    )

    assert integrated_model.requests == []
    assert len(work_order_model.requests) == 1
