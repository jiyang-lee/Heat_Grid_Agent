from __future__ import annotations

from typing import Protocol

from heatgrid_ops.agent.contracts import (
    AgentInputSnapshot,
    AgentLoopIterationRecord,
    AgentReviewRequest,
    AgentRunCompletion,
    AgentRunRequest,
    EvidenceCandidateStage,
)
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.run_models import (
    AgentRunResult,
    ArtifactRecord,
    AutomationPolicySnapshot,
    EvidenceCandidateSnapshot,
    EvidenceContextSnapshot,
    ModelInferenceSnapshot,
    ReviewTaskSnapshot,
)


class AgentInputPort(Protocol):
    async def load(self, request: AgentRunRequest) -> AgentInputSnapshot | None: ...


class AgentRunLifecyclePort(Protocol):
    async def mark_running(self, run_id: str) -> None: ...

    async def complete(
        self,
        run_id: str,
        completion: AgentRunCompletion,
    ) -> AgentRunResult: ...

    async def fail(self, run_id: str, error: str) -> AgentRunResult: ...


class AgentRunAuditPort(Protocol):
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


class AgentModelDataPort(Protocol):
    async def feature_values(self, card_id: str) -> dict[str, float]: ...

    async def active_artifact_uri(self) -> str | None: ...

    async def infer(
        self,
        feature_values: dict[str, float],
        source_input: JsonObject,
        active_artifact_uri: str | None,
    ) -> ModelInferenceSnapshot: ...


class AgentReviewPort(Protocol):
    async def automation_policy(self) -> AutomationPolicySnapshot: ...

    async def review_task(self, task_id: str) -> ReviewTaskSnapshot | None: ...

    async def create_review(self, request: AgentReviewRequest) -> ReviewTaskSnapshot: ...

    async def stage_evidence(
        self,
        stage: EvidenceCandidateStage,
    ) -> EvidenceCandidateSnapshot: ...


class AgentArtifactPort(Protocol):
    async def record(
        self,
        run_id: str,
        kind: str,
        name: str,
        uri: str,
    ) -> ArtifactRecord: ...


class AgentEvidenceContextPort(Protocol):
    def collect(
        self,
        card_id: str,
        source_input: JsonObject,
        top_k: int,
    ) -> EvidenceContextSnapshot: ...
