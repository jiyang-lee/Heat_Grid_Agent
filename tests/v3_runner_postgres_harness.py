from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Final
from uuid import uuid4

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from heatgrid_ops.agent.assessment import EvidenceAssessment
from heatgrid_ops.agent.contracts import AgentRunRequest
from heatgrid_ops.agent.graph import AgentGraphExecution
from heatgrid_ops.agent.models import (
    JsonObject,
    OpsAgentOutput,
    TokenUsage,
)
from heatgrid_ops.agent.review_capture import build_review_capture_source
from heatgrid_ops.agent.review_models import (
    AgentRunReviewCaptureSource,
    AgentRunReviewSnapshotV1,
)
from heatgrid_ops.agent.run_models import AgentRunResult
from heatgrid_ops.agent.state import (
    AgentState,
    EvidenceState,
    LoopState,
    OutputState,
    RequestState,
)
from heatgrid_rag.embedding import hash_embedding, vector_literal
from heatgrid_rag.pgstore import PgVectorStore


ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND_DIR: Final = (
    ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(BACKEND_DIR))

from simulator.versions.v2_postgres_react_ops.backend.agent_execution_migration import apply_agent_execution_migration  # noqa: E402
from simulator.versions.v2_postgres_react_ops.backend.agent_loop_repository import insert_agent_loop_iteration  # noqa: E402
from simulator.versions.v2_postgres_react_ops.backend.agent_review_snapshot_adapter import PostgresReviewSnapshotAdapter  # noqa: E402
from simulator.versions.v2_postgres_react_ops.backend.agent_run_repository import complete_agent_run  # noqa: E402
from simulator.versions.v2_postgres_react_ops.backend.schemas import (  # noqa: E402
    ModelVerificationResult as BackendModelVerificationResult,
    OpsAgentOutput as BackendOpsAgentOutput,
    SimulationResponse as BackendSimulationResponse,
    TokenUsage as BackendTokenUsage,
)


DEFAULT_DATABASE_URL: Final = "postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops"


@dataclass(frozen=True, slots=True)
class FailingSnapshotAdapter:
    real: PostgresReviewSnapshotAdapter

    async def capture(self, _snapshot: AgentRunReviewSnapshotV1) -> None:
        raise RuntimeError("secret=must-not-persist")

    async def mark_unavailable(self, run_id: str, reason: str) -> None:
        await self.real.mark_unavailable(run_id, reason)

    async def mark_pending(self, run_id: str) -> None:
        await self.real.mark_pending(run_id)


@dataclass(frozen=True, slots=True)
class RunnerPostgresHarness:
    engine: AsyncEngine
    database_url: str
    window_id: str
    decision_id: str
    card_id: str
    alert_id: str
    success_run_id: str
    failure_run_id: str
    legacy_run_id: str
    rag_document_id: str
    rag_chunk_id: str
    rag_query: str
    rag_source_path: str

    @classmethod
    async def create(cls) -> RunnerPostgresHarness:
        database_url = os.getenv("HEATGRID_TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
        await _apply_migrations(database_url)
        harness = cls(
            engine=create_async_engine(
                make_url(database_url).set(drivername="postgresql+asyncpg")
            ),
            database_url=database_url,
            window_id=str(uuid4()),
            decision_id=str(uuid4()),
            card_id=str(uuid4()),
            alert_id=str(uuid4()),
            success_run_id=str(uuid4()),
            failure_run_id=str(uuid4()),
            legacy_run_id=str(uuid4()),
            rag_document_id=f"runner-review-{uuid4()}",
            rag_chunk_id=f"runner-review-{uuid4()}",
            rag_query=f"operator manual {uuid4()}",
            rag_source_path=f"evidence/{uuid4()}.md",
        )
        try:
            await harness._seed()
        except Exception:
            await harness.engine.dispose()
            raise
        return harness

    @property
    def success_checkpoint_id(self) -> str:
        return f"checkpoint-{self.success_run_id}"

    def request(self, run_id: str) -> AgentRunRequest:
        return AgentRunRequest(
            run_id=run_id,
            alert_id=self.alert_id,
            card_id=self.card_id,
        )

    async def complete_graph(
        self,
        request: AgentRunRequest,
        *,
        include_capture: bool,
    ) -> AgentGraphExecution:
        await self._record_graph_lineage(request.run_id)
        await complete_agent_run(
            self.engine,
            request.run_id,
            BackendSimulationResponse(
                card_id=self.card_id,
                input_source="postgresql",
                agent_mode="fallback",
                ops_output=BackendOpsAgentOutput.model_validate(
                    _output().model_dump(mode="json")
                ),
                token_usage=BackendTokenUsage(total_tokens=90),
            ),
        )
        return AgentGraphExecution(
            result=_result(self, request.run_id),
            review_capture_source=(
                self.capture_source(request.run_id) if include_capture else None
            ),
        )

    def capture_source(self, run_id: str) -> AgentRunReviewCaptureSource:
        retrieval = PgVectorStore(self.database_url).search_chunks(
            self.rag_query,
            top_k=20,
        )
        state = AgentState(
            request=RequestState(
                run_id=run_id,
                alert_id=self.alert_id,
                card_id=self.card_id,
                source_input=_source_input(self),
            ),
            evidence=EvidenceState(external_context={"retrieval": retrieval}),
            loop=LoopState(
                assessment=EvidenceAssessment(
                    decision="request_human",
                    confidence=0.8,
                    evidence_score=0.9,
                    rationale="manual verification required",
                ),
                iteration=2,
            ),
            output=OutputState(
                value=_output(),
                token_usage=TokenUsage(total_tokens=90),
                mode="fallback",
            ),
        )
        return build_review_capture_source(state, _result(self, run_id))

    def failing_adapter_factory(self, _engine: AsyncEngine) -> FailingSnapshotAdapter:
        return FailingSnapshotAdapter(PostgresReviewSnapshotAdapter(self.engine))

    def real_adapter_factory(self, _engine: AsyncEngine) -> PostgresReviewSnapshotAdapter:
        return PostgresReviewSnapshotAdapter(self.engine)

    async def _seed(self) -> None:
        embedding = vector_literal(hash_embedding(self.rag_query))
        statements = (
            ("INSERT INTO substations (manufacturer_id, substation_id) VALUES ('maker', 31) ON CONFLICT (manufacturer_id, substation_id) DO NOTHING", {}),
            ("INSERT INTO windows (window_id, substation_uid, manufacturer_id, substation_id, window_start, window_end) VALUES (:window_id, (SELECT substation_uid FROM substations WHERE manufacturer_id = 'maker' AND substation_id = 31), 'maker', 31, now() - interval '1 hour', now())", {"window_id": self.window_id}),
            ("INSERT INTO priority_decisions (priority_decision_id, window_id, priority_level) VALUES (:decision_id, :window_id, 'high')", {"decision_id": self.decision_id, "window_id": self.window_id}),
            ("INSERT INTO priority_cards (card_id, priority_decision_id, review_required) VALUES (:card_id, :decision_id, true)", {"card_id": self.card_id, "decision_id": self.decision_id}),
            ("INSERT INTO ops_alert_queue (alert_id, card_id, substation_uid, manufacturer_id, substation_id, priority_level, enqueue_reason) VALUES (:alert_id, :card_id, (SELECT substation_uid FROM substations WHERE manufacturer_id = 'maker' AND substation_id = 31), 'maker', 31, 'high', 'runner review test')", {"alert_id": self.alert_id, "card_id": self.card_id}),
            ("INSERT INTO rag_documents (document_id, title, document_type, source_path, source_owner) VALUES (:document_id, 'Operator manual', 'operator_manual_evidence', :source_path, 'operations')", {"document_id": self.rag_document_id, "source_path": self.rag_source_path}),
            ("INSERT INTO rag_chunks (chunk_id, document_id, chunk_text, section_title, embedding) VALUES (:chunk_id, :document_id, :chunk_text, 'Inspection', CAST(:embedding AS vector))", {"chunk_id": self.rag_chunk_id, "document_id": self.rag_document_id, "chunk_text": self.rag_query, "embedding": embedding}),
        )
        async with self.engine.begin() as connection:
            for statement, params in statements:
                await connection.execute(text(statement), params)

    async def _record_graph_lineage(self, run_id: str) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                text("UPDATE agent_run_tasks SET checkpoint_id = :checkpoint_id WHERE run_id = :run_id"),
                {"run_id": run_id, "checkpoint_id": f"checkpoint-{run_id}"},
            )
        verification = BackendModelVerificationResult(
            status="verified",
            agreement=True,
        )
        for iteration, decision in ((1, "rerun_model"), (2, "request_human")):
            await insert_agent_loop_iteration(
                self.engine,
                run_id=run_id,
                iteration=iteration,
                phase="assessment",
                decision=decision,
                confidence=0.8,
                evidence_score=0.9,
                missing_evidence=[],
                model_verification=verification,
            )


async def _apply_migrations(database_url: str) -> None:
    pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        conninfo=database_url.replace("postgresql+asyncpg://", "postgresql://", 1),
        min_size=1,
        max_size=1,
        open=False,
        kwargs={"autocommit": True, "row_factory": dict_row},
    )
    await pool.open()
    try:
        await apply_agent_execution_migration(pool)
    finally:
        await pool.close()


def _source_input(harness: RunnerPostgresHarness) -> JsonObject:
    return {
        "priority_context": {
            "card": {"status": "open", "review_required": True},
            "priority": {"priority_level": "urgent"},
            "explanation": {"why_reason": "manual verification"},
        },
        "raw_context": {
            "window": {"substation_id": 31, "manufacturer_id": "maker"}
        },
        "card_id": harness.card_id,
    }


def _output() -> OpsAgentOutput:
    return OpsAgentOutput(summary="stable", action_plan="monitor", caution="review")


def _result(harness: RunnerPostgresHarness, run_id: str) -> AgentRunResult:
    return AgentRunResult(
        run_id=run_id,
        status="completed",
        input_source="alert",
        alert_id=harness.alert_id,
        card_id=harness.card_id,
        agent_mode="fallback",
        ops_output=_output(),
        token_usage=TokenUsage(total_tokens=90),
    )
