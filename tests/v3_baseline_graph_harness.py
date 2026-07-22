from __future__ import annotations

from dataclasses import dataclass

from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.contracts import AgentRunRequest
from heatgrid_ops.agent.graph import AgentGraphContext, execute_agent_graph
from heatgrid_ops.agent.services import AgentRuntime
from v3_baseline_fake_ports import (
    FakeArtifactPort,
    FakeBudgetPort,
    FakeChatModelPort,
    FakeDiagnosticModel,
    FakeExternalDataPort,
    FakeInputPort,
    FakeLifecyclePort,
    FakeModelVerificationPort,
    FakeRagPort,
    FakeReportWriterPort,
    FakeReviewPort,
    RecordingAudit,
)


@dataclass(frozen=True, slots=True)
class GraphScenario:
    priority_level: str
    review_required: bool
    rag_chunk_count: int
    agreement: bool


@dataclass(frozen=True, slots=True)
class GraphReplay:
    decisions: tuple[str, ...]
    loop_count: int
    terminal_status: str


async def replay_graph(scenario: GraphScenario) -> GraphReplay:
    audit = RecordingAudit()
    runtime = AgentRuntime(
        config=AgentRuntimeConfig(
            openai_model="fixed-model",
            rag_top_k=5,
            agent_max_iterations=4,
            agent_evidence_threshold=0.75,
            model_score_tolerance=0.05,
            input_usd_per_1m=0.0,
            cached_input_usd_per_1m=0.0,
            output_usd_per_1m=0.0,
            pricing_source="test",
        ),
        rag=FakeRagPort(scenario.rag_chunk_count),
        external_data=FakeExternalDataPort(),
        chat_model=FakeChatModelPort(),
        model_verification=FakeModelVerificationPort(scenario.agreement),
        report_writer=FakeReportWriterPort(),
        diagnostic_model=FakeDiagnosticModel(),
    )
    result = await execute_agent_graph(
        AgentGraphContext(
            runtime=runtime,
            inputs=FakeInputPort(
                priority_level=scenario.priority_level,
                review_required=scenario.review_required,
            ),
            lifecycle=FakeLifecyclePort(),
            audit=audit,
            reviews=FakeReviewPort(),
            artifacts=FakeArtifactPort(),
            budget=FakeBudgetPort(),
        ),
        AgentRunRequest(
            run_id="run-baseline",
            alert_id="alert-baseline",
            card_id="card-baseline",
        ),
    )
    return GraphReplay(
        decisions=tuple(audit.decisions),
        loop_count=len(audit.decisions),
        terminal_status=result.status,
    )
