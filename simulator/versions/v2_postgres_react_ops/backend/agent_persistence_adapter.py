from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from agent_loop_repository import insert_agent_loop_iteration
from agent_run_artifact_repository import insert_agent_run_artifact
from agent_run_event_repository import AgentRunEventRecord
from agent_run_repository import (
    complete_agent_run,
    fail_agent_run,
    mark_agent_run_running,
    record_agent_run_event,
)
from heatgrid_ops.agent.contracts import AgentLoopIterationRecord, AgentRunCompletion
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.run_models import AgentRunResult, ArtifactRecord
from schemas import (
    AgentLoopSummary as BackendAgentLoopSummary,
    ModelVerificationResult as BackendModelVerificationResult,
    SimulationResponse as BackendSimulationResponse,
)


@dataclass(frozen=True, slots=True)
class PostgresAgentPersistenceAdapter:
    engine: AsyncEngine

    async def mark_running(self, run_id: str) -> None:
        await mark_agent_run_running(self.engine, run_id)

    async def complete(
        self,
        run_id: str,
        completion: AgentRunCompletion,
    ) -> AgentRunResult:
        simulation = BackendSimulationResponse.model_validate(
            completion.simulation.model_dump(mode="json")
        )
        loop_summary = BackendAgentLoopSummary.model_validate(
            completion.loop_summary.model_dump(mode="json")
        )
        run = await complete_agent_run(
            self.engine,
            run_id,
            simulation,
            loop_summary=loop_summary,
            review_task_id=completion.review_task_id,
        )
        return AgentRunResult.model_validate(run.model_dump(mode="json"))

    async def fail(self, run_id: str, error: str) -> AgentRunResult:
        run = await fail_agent_run(self.engine, run_id, error)
        return AgentRunResult.model_validate(run.model_dump(mode="json"))

    async def record_event(
        self,
        run_id: str,
        event_type: str,
        message: str,
        payload: JsonObject,
    ) -> None:
        await record_agent_run_event(
            self.engine,
            AgentRunEventRecord(
                run_id=run_id,
                event_type=event_type,
                message=message,
                payload=payload,
            ),
        )

    async def record_loop_iteration(
        self,
        record: AgentLoopIterationRecord,
    ) -> None:
        verification = (
            None
            if record.model_verification is None
            else BackendModelVerificationResult.model_validate(
                record.model_verification.model_dump(mode="json")
            )
        )
        await insert_agent_loop_iteration(
            self.engine,
            run_id=record.run_id,
            iteration=record.iteration,
            phase=record.phase,
            decision=record.decision,
            confidence=record.confidence,
            evidence_score=record.evidence_score,
            missing_evidence=record.missing_evidence,
            model_verification=verification,
        )

    async def record(
        self,
        run_id: str,
        kind: str,
        name: str,
        uri: str,
    ) -> ArtifactRecord:
        artifact = await insert_agent_run_artifact(
            self.engine,
            run_id=run_id,
            kind=kind,
            name=name,
            uri=uri,
        )
        return ArtifactRecord.model_validate(artifact.model_dump(mode="json"))
