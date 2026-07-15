from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from heatgrid_ops.agent.assessment import EvidenceAssessment
from heatgrid_ops.agent.contracts import (
    AgentInputSnapshot,
    ChatModelRequest,
    EvidenceAssessmentRequest,
    AgentLoopIterationRecord,
    AgentReviewRequest,
    AgentRunCompletion,
    AgentRunRequest,
    ReportWriteRequest,
)
from heatgrid_ops.agent.diagnostics import DiagnosticBudgetReservation
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.run_models import (
    AgentRunResult,
    AgentStreamEvent,
    ArtifactRecord,
    ChatModelResult,
    ChatModelAssessmentResult,
    ExternalDataRequest,
    ExternalDataSnapshot,
    ModelVerificationRequest,
    ModelVerificationSnapshot,
    RagEvidenceRequest,
    RagEvidenceSnapshot,
    ReportArtifactDraft,
    ReviewTaskSnapshot,
)


class AgentInputPort(Protocol):
    async def load(self, request: AgentRunRequest) -> AgentInputSnapshot | None: ...


class RunLifecyclePort(Protocol):
    async def mark_running(self, run_id: str) -> None: ...

    async def complete(
        self,
        run_id: str,
        completion: AgentRunCompletion,
    ) -> AgentRunResult: ...

    async def fail(self, run_id: str, error: str) -> AgentRunResult: ...


class RunAuditPort(Protocol):
    async def record_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        payload: JsonObject,
    ) -> None: ...

    async def record_loop_iteration(
        self,
        record: AgentLoopIterationRecord,
    ) -> None: ...


class ReviewPort(Protocol):
    async def create_review(
        self, request: AgentReviewRequest
    ) -> ReviewTaskSnapshot: ...


class ArtifactPort(Protocol):
    async def record(
        self,
        run_id: str,
        kind: str,
        name: str,
        uri: str,
    ) -> ArtifactRecord: ...


class ExternalDataPort(Protocol):
    async def snapshot(self, request: ExternalDataRequest) -> ExternalDataSnapshot: ...


class RagEvidencePort(Protocol):
    async def search(self, request: RagEvidenceRequest) -> RagEvidenceSnapshot: ...


class ChatModelPort(Protocol):
    async def generate(self, request: ChatModelRequest) -> ChatModelResult: ...

    async def assess(
        self,
        request: EvidenceAssessmentRequest,
    ) -> ChatModelAssessmentResult | EvidenceAssessment | None: ...

    def stream(self, request: ChatModelRequest) -> AsyncIterator[AgentStreamEvent]: ...


class AgentBudgetPort(Protocol):
    async def reserve_diagnostic(
        self,
        run_id: str,
        token_limit: int,
    ) -> DiagnosticBudgetReservation: ...

    async def finish_diagnostic(
        self,
        reservation_id: str,
        *,
        tokens_used: int,
        model_called: bool,
    ) -> None: ...


class ModelVerificationPort(Protocol):
    async def verify(
        self,
        request: ModelVerificationRequest,
    ) -> ModelVerificationSnapshot: ...


class ReportWriterPort(Protocol):
    async def write_anomaly(
        self,
        request: ReportWriteRequest,
    ) -> ReportArtifactDraft: ...

    async def write_daily(
        self,
        request: ReportWriteRequest,
    ) -> ReportArtifactDraft: ...
