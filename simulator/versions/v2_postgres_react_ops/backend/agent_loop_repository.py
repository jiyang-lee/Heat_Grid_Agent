from __future__ import annotations

from typing import Final

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from schemas import AgentLoopIteration, ModelVerificationResult

AGENT_LOOP_ITERATIONS_DDL: Final = """
CREATE TABLE IF NOT EXISTS agent_loop_iterations (
    iteration_id bigserial PRIMARY KEY,
    run_id uuid NOT NULL,
    iteration integer NOT NULL,
    phase text NOT NULL,
    decision text NOT NULL,
    confidence double precision NOT NULL,
    evidence_score double precision NOT NULL,
    missing_evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
    model_verification jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
)
"""

AGENT_LOOP_ITERATIONS_INDEX_DDL: Final = """
CREATE INDEX IF NOT EXISTS agent_loop_iterations_run_idx
ON agent_loop_iterations(run_id, iteration_id)
"""


async def ensure_agent_loop_iteration_table(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(text(AGENT_LOOP_ITERATIONS_DDL))
        await connection.execute(text(AGENT_LOOP_ITERATIONS_INDEX_DDL))


async def insert_agent_loop_iteration(
    engine: AsyncEngine,
    *,
    run_id: str,
    iteration: int,
    phase: str,
    decision: str,
    confidence: float,
    evidence_score: float,
    missing_evidence: list[str],
    model_verification: ModelVerificationResult | None,
) -> AgentLoopIteration:
    await ensure_agent_loop_iteration_table(engine)
    query = text(
        "INSERT INTO agent_loop_iterations ("
        "run_id, iteration, phase, decision, confidence, evidence_score, "
        "missing_evidence, model_verification"
        ") VALUES ("
        ":run_id, :iteration, :phase, :decision, :confidence, :evidence_score, "
        "CAST(:missing_evidence AS jsonb), CAST(:model_verification AS jsonb)"
        ") ON CONFLICT (run_id, iteration, phase) DO UPDATE SET "
        "decision = EXCLUDED.decision, confidence = EXCLUDED.confidence, "
        "evidence_score = EXCLUDED.evidence_score, "
        "missing_evidence = EXCLUDED.missing_evidence, "
        "model_verification = EXCLUDED.model_verification "
        "RETURNING iteration_id, run_id, iteration, phase, decision, confidence, "
        "evidence_score, CAST(missing_evidence AS text) AS missing_evidence, "
        "CAST(model_verification AS text) AS model_verification, created_at"
    )
    params = {
        "run_id": run_id,
        "iteration": iteration,
        "phase": phase,
        "decision": decision,
        "confidence": confidence,
        "evidence_score": evidence_score,
        "missing_evidence": orjson.dumps(missing_evidence).decode("utf-8"),
        "model_verification": orjson.dumps(
            None if model_verification is None else model_verification.model_dump(mode="json")
        ).decode("utf-8"),
    }
    async with engine.begin() as connection:
        result = await connection.execute(query, params)
    return _iteration_from_row(result.mappings().one())


async def list_agent_loop_iterations(
    engine: AsyncEngine,
    run_id: str,
) -> list[AgentLoopIteration]:
    await ensure_agent_loop_iteration_table(engine)
    query = text(
        "SELECT iteration_id, run_id, iteration, phase, decision, confidence, "
        "evidence_score, CAST(missing_evidence AS text) AS missing_evidence, "
        "CAST(model_verification AS text) AS model_verification, created_at "
        "FROM agent_loop_iterations WHERE run_id = :run_id ORDER BY iteration_id"
    )
    async with engine.connect() as connection:
        result = await connection.execute(query, {"run_id": run_id})
    return [_iteration_from_row(row) for row in result.mappings().all()]


def _iteration_from_row(row: RowMapping) -> AgentLoopIteration:
    verification = row["model_verification"]
    return AgentLoopIteration(
        iteration_id=int(row["iteration_id"]),
        run_id=str(row["run_id"]),
        iteration=int(row["iteration"]),
        phase=str(row["phase"]),
        decision=str(row["decision"]),
        confidence=float(row["confidence"]),
        evidence_score=float(row["evidence_score"]),
        missing_evidence=orjson.loads(row["missing_evidence"]),
        model_verification=None
        if verification is None
        else ModelVerificationResult.model_validate(orjson.loads(verification)),
        created_at=row["created_at"].isoformat(),
    )
