from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from heatgrid_ops.agent.assessment import EvidenceAssessment
from heatgrid_ops.agent.contracts import (
    AgentInputSnapshot,
    AgentLoopIterationRecord,
    AgentReviewRequest,
    AgentRunCompletion,
    AgentRunRequest,
    ChatModelRequest,
    EvidenceAssessmentRequest,
    ReportWriteRequest,
)
from heatgrid_ops.agent.diagnostics import (
    DiagnosticBudgetReservation,
    DiagnosticHypothesis,
    DiagnosticModelResult,
    DiagnosticWorkerInput,
    DiagnosticWorkerOutput,
)
from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.models import (
    JsonObject,
    JsonValue,
    ModelVerificationResult,
    TokenCall,
)
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


@dataclass(slots=True)
class RecordingAudit:
    decisions: list[str] = field(default_factory=list)

    async def record_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        payload: JsonObject,
    ) -> None:
        assert run_id == "run-baseline"

    async def record_loop_iteration(self, record: AgentLoopIterationRecord) -> None:
        self.decisions.append(record.decision)


@dataclass(frozen=True, slots=True)
class FakeInputPort:
    priority_level: str
    review_required: bool

    async def load(self, request: AgentRunRequest) -> AgentInputSnapshot | None:
        source_input: JsonObject = {
            "card_id": request.card_id,
            "sections": {},
            "priority_context": {
                "card": {
                    "card_id": request.card_id,
                    "review_required": self.review_required,
                },
                "priority": {"priority_level": self.priority_level},
                "explanation": {
                    "recommended_action": "Inspect the heat exchanger."
                },
            },
            "raw_context": {
                "window": {
                    "manufacturer_id": "manufacturer-1",
                    "substation_id": 31,
                    "window_start": "2020-01-11T00:00:00+09:00",
                    "window_end": "2020-01-11T06:00:00+09:00",
                },
                "sensor_summaries": [],
            },
        }
        return AgentInputSnapshot(source_input=source_input)


class FakeLifecyclePort:
    async def mark_running(self, run_id: str) -> None:
        assert run_id == "run-baseline"

    async def complete(
        self,
        run_id: str,
        completion: AgentRunCompletion,
    ) -> AgentRunResult:
        return AgentRunResult(
            run_id=run_id,
            status="completed",
            input_source="alert",
            alert_id="alert-baseline",
            card_id=completion.simulation.card_id,
            agent_mode=completion.simulation.agent_mode,
            ops_output=completion.simulation.ops_output,
            token_usage=completion.simulation.token_usage,
            loop_summary=completion.loop_summary,
            review_task_id=completion.review_task_id,
        )

    async def fail(self, run_id: str, error: str) -> AgentRunResult:
        raise AssertionError((run_id, error))


class FakeReviewPort:
    async def create_review(self, request: AgentReviewRequest) -> ReviewTaskSnapshot:
        return ReviewTaskSnapshot(
            task_id=f"review-{request.task_type}",
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
            artifact_id="artifact-baseline",
            run_id=run_id,
            kind=kind,
            name=name,
            uri=uri,
        )


@dataclass(frozen=True, slots=True)
class FakeRagPort:
    chunk_count: int

    async def search(self, request: RagEvidenceRequest) -> RagEvidenceSnapshot:
        chunks: list[JsonValue] = []
        for index in range(self.chunk_count):
            chunks.append(
                {
                    "chunk_id": f"rag-{index + 1}",
                    "text": "deterministic inspection reference",
                    "source": "manual.pdf",
                    "title": "Operations manual",
                    "score": 0.9 - index / 100,
                }
            )
        return RagEvidenceSnapshot(
            status="available" if chunks else "no_match",
            retrieval={
                "status": "available" if chunks else "no_match",
                "chunks": chunks,
            },
            references={},
        )


class FakeExternalDataPort:
    async def snapshot(self, request: ExternalDataRequest) -> ExternalDataSnapshot:
        return ExternalDataSnapshot(
            status="available",
            site={"status": "mapped", "substation_id": request.substation_id},
            weather={
                "status": "available",
                "temperature_c": -2.0,
                "provenance": {"source": "fixed_weather"},
            },
        )


class FakeChatModelPort:
    async def generate(self, request: ChatModelRequest) -> ChatModelResult:
        raise AgentDependencyError(service="llm", detail="disabled in baseline")

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


@dataclass(frozen=True, slots=True)
class FakeModelVerificationPort:
    agreement: bool

    async def verify(
        self,
        request: ModelVerificationRequest,
    ) -> ModelVerificationSnapshot:
        return ModelVerificationSnapshot(
            result=ModelVerificationResult(
                status="verified",
                attempt=request.attempt,
                agreement=self.agreement,
            ),
            artifact_uri="models/fixed.joblib",
        )


class FakeReportWriterPort:
    async def write_anomaly(
        self,
        request: ReportWriteRequest,
    ) -> ReportArtifactDraft:
        return ReportArtifactDraft(
            kind="anomaly_report",
            name="anomaly_report.json",
            uri=f"output/{request.run_id}/anomaly_report.json",
        )

    async def write_daily(self, request: ReportWriteRequest) -> ReportArtifactDraft:
        raise AssertionError("daily report is outside the graph")


class FakeDiagnosticModel:
    async def diagnose(self, request: DiagnosticWorkerInput) -> DiagnosticModelResult:
        return DiagnosticModelResult(
            output=DiagnosticWorkerOutput(
                hypotheses=[
                    DiagnosticHypothesis(
                        hypothesis_id="hypothesis-1",
                        title="Inspection reference match",
                        rationale="The cited reference describes the same pattern.",
                        evidence_ids=[request.rag_chunks[0].evidence_id],
                        confidence=0.7,
                    )
                ]
            ),
            calls=[TokenCall(input_tokens=500, output_tokens=80, total_tokens=580)],
        )


class FakeBudgetPort:
    async def reserve_diagnostic(
        self,
        run_id: str,
        token_limit: int,
    ) -> DiagnosticBudgetReservation:
        assert token_limit == 4_000
        return DiagnosticBudgetReservation(reservation_id="budget-1", granted=True)

    async def finish_diagnostic(
        self,
        reservation_id: str,
        *,
        tokens_used: int,
        model_called: bool,
    ) -> None:
        assert reservation_id == "budget-1"
        assert tokens_used <= 4_000
        assert model_called is True
