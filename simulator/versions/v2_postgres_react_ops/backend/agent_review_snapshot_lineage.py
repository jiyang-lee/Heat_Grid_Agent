from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.agent.diagnostics import (
    DIAGNOSTIC_INPUT_TOKEN_LIMIT,
    DIAGNOSTIC_OUTPUT_TOKEN_LIMIT,
)
from heatgrid_ops.agent.review_models import (
    AgentRunReviewCaptureSource,
    AgentRunReviewSnapshotV1,
    ReviewBudgetLineage,
    ReviewCheckpointLineage,
    ReviewDecisionStep,
    ReviewEvidenceSnapshot,
    ReviewSourceCardSnapshot,
)


@dataclass(frozen=True, slots=True)
class AgentReviewSnapshotLineage:
    decisions: tuple[ReviewDecisionStep, ...]
    budget: ReviewBudgetLineage
    checkpoint: ReviewCheckpointLineage


@dataclass(frozen=True, slots=True)
class ReviewSnapshotAssemblyError(Exception):
    detail: str

    def __str__(self) -> str:
        return self.detail


async def load_review_snapshot_lineage(
    engine: AsyncEngine,
    run_id: str,
) -> AgentReviewSnapshotLineage:
    async with engine.connect() as connection:
        decision_result = await connection.execute(
            text(
                "SELECT decision, phase FROM agent_loop_iterations "
                "WHERE run_id = :run_id ORDER BY iteration_id"
            ),
            {"run_id": run_id},
        )
        lineage_result = await connection.execute(
            text(
                "SELECT tasks.checkpoint_thread_id, tasks.checkpoint_namespace, "
                "tasks.checkpoint_id, parent.token_limit AS parent_token_limit, "
                "parent.tokens_used AS parent_tokens_used, "
                "diagnostic.token_limit AS diagnostic_token_limit, "
                "diagnostic.tokens_used AS diagnostic_tokens_used "
                "FROM agent_run_tasks tasks "
                "JOIN agent_budget_ledger parent "
                "ON parent.task_id = tasks.task_id "
                "AND parent.parent_ledger_id IS NULL "
                "LEFT JOIN agent_budget_ledger diagnostic "
                "ON diagnostic.parent_ledger_id = parent.ledger_id "
                "AND diagnostic.operation_key = :diagnostic_operation_key "
                "WHERE tasks.run_id = :run_id AND tasks.task_key = 'agent_graph:v1'"
            ),
            {
                "run_id": run_id,
                "diagnostic_operation_key": (
                    f"diagnostic-budget:{run_id}:fault_diagnosis:v1"
                ),
            },
        )
    lineage = lineage_result.mappings().one_or_none()
    if lineage is None or lineage["parent_tokens_used"] is None:
        raise ReviewSnapshotAssemblyError("completed run lineage is incomplete")
    decisions = tuple(
        ReviewDecisionStep(
            sequence=sequence,
            decision=str(row["decision"])[:120],
            reason=(str(row["phase"]) or "recorded decision")[:1000],
        )
        for sequence, row in enumerate(decision_result.mappings().all(), start=1)
    )
    return AgentReviewSnapshotLineage(
        decisions=decisions,
        budget=ReviewBudgetLineage(
            parent_token_limit=int(lineage["parent_token_limit"]),
            parent_tokens_used=int(lineage["parent_tokens_used"]),
            diagnostic_token_limit=(
                DIAGNOSTIC_INPUT_TOKEN_LIMIT + DIAGNOSTIC_OUTPUT_TOKEN_LIMIT
                if lineage["diagnostic_token_limit"] is None
                else int(lineage["diagnostic_token_limit"])
            ),
            diagnostic_tokens_used=(
                0
                if lineage["diagnostic_tokens_used"] is None
                else int(lineage["diagnostic_tokens_used"])
            ),
        ),
        checkpoint=ReviewCheckpointLineage(
            thread_id=str(lineage["checkpoint_thread_id"]),
            namespace=str(lineage["checkpoint_namespace"]),
            checkpoint_id=(
                None
                if lineage["checkpoint_id"] is None
                else str(lineage["checkpoint_id"])
            ),
        ),
    )


def assemble_review_snapshot(
    source: AgentRunReviewCaptureSource,
    lineage: AgentReviewSnapshotLineage,
) -> AgentRunReviewSnapshotV1:
    card = source.source_card
    if card.priority_level is None:
        raise ReviewSnapshotAssemblyError("source card priority is missing")
    if card.reason is None:
        raise ReviewSnapshotAssemblyError("source card reason is missing")
    evidence: list[ReviewEvidenceSnapshot] = []
    for item in source.evidence:
        if item.provenance is None:
            raise ReviewSnapshotAssemblyError(
                f"evidence provenance is missing: {item.evidence_id}"
            )
        evidence.append(
            ReviewEvidenceSnapshot(
                evidence_id=item.evidence_id,
                document_type=item.document_type,
                source_owner=item.source_owner,
                source=item.source,
                title=item.title,
                section=item.section,
                score=item.score,
                excerpt=item.excerpt,
                provenance=item.provenance,
            )
        )
    return AgentRunReviewSnapshotV1(
        run_id=source.run_id,
        result=source.result,
        decisions=lineage.decisions,
        loop_count=source.loop_count,
        handling_reason=source.handling_reason,
        diagnostic=source.diagnostic,
        model_verification=source.model_verification,
        weather=source.weather,
        evidence=tuple(evidence),
        source_card=ReviewSourceCardSnapshot(
            card_id=card.card_id,
            substation_id=card.substation_id,
            manufacturer_id=card.manufacturer_id,
            priority_level=card.priority_level,
            status=card.status,
            review_required=card.review_required,
            reason=card.reason,
        ),
        budget=lineage.budget,
        checkpoint=lineage.checkpoint,
    )
