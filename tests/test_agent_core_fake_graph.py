from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from heatgrid_ops.agent.assessment import EvidenceAssessment
from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.contracts import (
    AgentInputSnapshot,
    AgentReviewRequest,
    AgentRunCompletion,
    AgentRunRequest,
    ChatModelRequest,
    EvidenceAssessmentRequest,
    ReportWriteRequest,
)
from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.graph import AgentGraphContext, execute_agent_graph
from heatgrid_ops.agent.diagnostics import (
    DiagnosticBudgetReservation,
    DiagnosticHypothesis,
    DiagnosticModelResult,
    DiagnosticWorkerInput,
    DiagnosticWorkerOutput,
)
from heatgrid_ops.agent.models import ModelVerificationResult, TokenCall
from heatgrid_ops.agent.run_models import (
    AgentRunResult,
    AgentStreamEvent,
    ArtifactRecord,
    ChatModelResult,
    ExternalDataRequest,
    ExternalDataSnapshot,
    ModelVerificationRequest,
    ModelVerificationSnapshot,
    RagEvidenceRequest,
    RagEvidenceSnapshot,
    ReportArtifactDraft,
    ReviewTaskSnapshot,
)
from heatgrid_ops.agent.services import AgentRuntime


class FakeInputPort:
    async def load(self, request: AgentRunRequest) -> AgentInputSnapshot | None:
        return AgentInputSnapshot(source_input=_source_input(request.card_id))


class FakeLifecyclePort:
    async def mark_running(self, run_id: str) -> None:
        assert run_id == "run-1"

    async def complete(
        self,
        run_id: str,
        completion: AgentRunCompletion,
    ) -> AgentRunResult:
        return AgentRunResult(
            run_id=run_id,
            status="completed",
            input_source="alert",
            alert_id="alert-1",
            card_id=completion.simulation.card_id,
            agent_mode=completion.simulation.agent_mode,
            ops_output=completion.simulation.ops_output,
            token_usage=completion.simulation.token_usage,
            loop_summary=completion.loop_summary,
            review_task_id=completion.review_task_id,
        )

    async def fail(self, run_id: str, error: str) -> AgentRunResult:
        raise AssertionError((run_id, error))


class FakeAuditPort:
    async def record_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        payload: dict,
    ) -> None:
        assert run_id == "run-1"

    async def record_loop_iteration(self, record) -> None:
        assert record.run_id == "run-1"


class FakeReviewPort:
    async def create_review(self, request: AgentReviewRequest) -> ReviewTaskSnapshot:
        return ReviewTaskSnapshot(
            task_id="review-1",
            task_type=request.task_type,
            status="pending",
        )


class FakeArtifactPort:
    async def record(
        self,
        run_id: str,
        kind: str,
        name: str,
        uri: str,
    ) -> ArtifactRecord:
        return ArtifactRecord(
            artifact_id="artifact-1",
            run_id=run_id,
            kind=kind,
            name=name,
            uri=uri,
        )


class FakeRagPort:
    async def search(self, request: RagEvidenceRequest) -> RagEvidenceSnapshot:
        return RagEvidenceSnapshot(
            status="available",
            retrieval={
                "status": "available",
                "chunks": [
                    {"chunk_id": "rag-1", "text": "inspection reference"},
                    {"chunk_id": "rag-2", "text": "operation reference"},
                ],
            },
            references={},
        )


class FakeExternalDataPort:
    def __init__(self) -> None:
        self.calls = 0

    async def snapshot(self, request: ExternalDataRequest) -> ExternalDataSnapshot:
        self.calls += 1
        assert request.substation_id == 31
        return ExternalDataSnapshot(
            status="available",
            site={"status": "mapped", "substation_id": 31},
            weather={"status": "available", "temperature_c": -2.0},
        )


class FakeChatModelPort:
    async def generate(self, request: ChatModelRequest) -> ChatModelResult:
        raise AgentDependencyError(service="llm", detail="model disabled in fake graph")

    async def assess(
        self,
        request: EvidenceAssessmentRequest,
    ) -> EvidenceAssessment | None:
        return None

    async def stream(
        self,
        request: ChatModelRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        if False:
            yield AgentStreamEvent(kind="llm", message="unused")


class FakeModelVerificationPort:
    async def verify(
        self,
        request: ModelVerificationRequest,
    ) -> ModelVerificationSnapshot:
        return ModelVerificationSnapshot(
            result=ModelVerificationResult(
                status="verified",
                attempt=request.attempt,
                agreement=True,
            ),
            artifact_uri="models/fake.joblib",
        )


class FakeReportWriterPort:
    async def write_anomaly(
        self,
        request: ReportWriteRequest,
    ) -> ReportArtifactDraft:
        return ReportArtifactDraft(
            kind="anomaly_report",
            name="anomaly_report.json",
            uri=f"output/ops_agent/reports/{request.run_id}/anomaly_report.json",
        )

    async def write_daily(
        self,
        request: ReportWriteRequest,
    ) -> ReportArtifactDraft:
        raise AssertionError("daily report is not part of the graph")


class FakeDiagnosticModel:
    def __init__(self) -> None:
        self.calls = 0

    async def diagnose(self, request: DiagnosticWorkerInput) -> DiagnosticModelResult:
        self.calls += 1
        return DiagnosticModelResult(
            output=DiagnosticWorkerOutput(
                hypotheses=[
                    DiagnosticHypothesis(
                        hypothesis_id="hypothesis-1",
                        title="Inspection reference match",
                        rationale="The internal reference describes the same pattern.",
                        evidence_ids=[request.rag_chunks[0].evidence_id],
                        confidence=0.7,
                    )
                ]
            ),
            calls=[TokenCall(input_tokens=500, output_tokens=80, total_tokens=580)],
        )


class FakeBudgetPort:
    def __init__(self) -> None:
        self.reserved = 0
        self.settled = 0

    async def reserve_diagnostic(
        self,
        run_id: str,
        token_limit: int,
    ) -> DiagnosticBudgetReservation:
        assert run_id == "run-1"
        self.reserved = token_limit
        return DiagnosticBudgetReservation(
            reservation_id="budget-1",
            granted=True,
        )

    async def finish_diagnostic(
        self,
        reservation_id: str,
        *,
        tokens_used: int,
        model_called: bool,
    ) -> None:
        assert reservation_id == "budget-1"
        assert model_called is True
        self.settled = tokens_used


@pytest.mark.anyio
async def test_graph_executes_with_core_ports_only() -> None:
    await run_fake_graph()


@pytest.mark.anyio
async def test_graph_runs_read_only_diagnostic_once_then_requests_review() -> None:
    diagnostic_model = FakeDiagnosticModel()
    budget = FakeBudgetPort()
    runtime = _runtime(FakeExternalDataPort(), diagnostic_model=diagnostic_model)
    context = AgentGraphContext(
        runtime=runtime,
        inputs=FakeInputPort(),
        lifecycle=FakeLifecyclePort(),
        audit=FakeAuditPort(),
        reviews=FakeReviewPort(),
        artifacts=FakeArtifactPort(),
        budget=budget,
    )

    result = await execute_agent_graph(
        context,
        AgentRunRequest(run_id="run-1", alert_id="alert-1", card_id="card-1"),
    )

    assert result.loop_summary is not None
    assert result.loop_summary.decision == "request_human"
    assert diagnostic_model.calls == 1
    assert budget.reserved == 4_000
    assert 0 < budget.settled <= 4_000


async def run_fake_graph() -> None:
    external_data = FakeExternalDataPort()
    runtime = _runtime(external_data)
    context = AgentGraphContext(
        runtime=runtime,
        inputs=FakeInputPort(),
        lifecycle=FakeLifecyclePort(),
        audit=FakeAuditPort(),
        reviews=FakeReviewPort(),
        artifacts=FakeArtifactPort(),
    )

    result = await execute_agent_graph(
        context,
        AgentRunRequest(run_id="run-1", alert_id="alert-1", card_id="card-1"),
    )

    assert result.status == "completed"
    assert result.card_id == "card-1"
    assert result.agent_mode == "fallback"
    assert result.loop_summary is not None
    assert result.loop_summary.decision == "finalize"
    assert external_data.calls == 1


def _runtime(
    external_data: FakeExternalDataPort,
    *,
    diagnostic_model: FakeDiagnosticModel | None = None,
) -> AgentRuntime:
    return AgentRuntime(
        config=AgentRuntimeConfig(
            openai_model="fake-model",
            rag_top_k=5,
            agent_max_iterations=4,
            agent_evidence_threshold=0.75,
            model_score_tolerance=0.05,
            input_usd_per_1m=0.0,
            cached_input_usd_per_1m=0.0,
            output_usd_per_1m=0.0,
            pricing_source="test",
        ),
        rag=FakeRagPort(),
        external_data=external_data,
        chat_model=FakeChatModelPort(),
        model_verification=FakeModelVerificationPort(),
        report_writer=FakeReportWriterPort(),
        diagnostic_model=diagnostic_model,
    )


def _source_input(card_id: str) -> dict:
    return {
        "card_id": card_id,
        "sections": {},
        "priority_context": {
            "card": {"card_id": card_id, "review_required": False},
            "priority": {"priority_level": "high"},
            "explanation": {"recommended_action": "Inspect the heat exchanger."},
        },
        "raw_context": {
            "window": {
                "manufacturer_id": "manufacturer 1",
                "substation_id": 31,
                "window_start": "2020-01-11T00:00:00+09:00",
                "window_end": "2020-01-11T06:00:00+09:00",
            },
            "sensor_summaries": [],
        },
    }
