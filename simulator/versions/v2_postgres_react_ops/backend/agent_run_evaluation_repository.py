from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy.ext.asyncio import AsyncEngine

from agent_review_api_models import (
    AgentRunEvaluationItem,
    AgentRunEvaluationPage,
    CitationCoverage,
    EvidenceCompleteness,
    InputValidity,
    OperatorReviewStatus,
    ParentHandling,
    WorkerStatus,
)
from agent_review_snapshot_repository import get_review_snapshot
from agent_run_listing_repository import (
    AgentRunCursor,
    AgentRunListFilters,
    list_agent_runs,
)
from heatgrid_ops.agent.review_models import AgentRunReviewSnapshotV1


@dataclass(frozen=True, slots=True)
class AgentRunEvaluationFilters:
    run_id: str | None = None
    worker_status: WorkerStatus | None = None
    parent_handling: ParentHandling | None = None
    operator_review_status: OperatorReviewStatus | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    cursor: AgentRunCursor | None = None
    limit: int = 50


async def list_agent_run_evaluations(
    engine: AsyncEngine,
    filters: AgentRunEvaluationFilters,
) -> AgentRunEvaluationPage:
    runs = await list_agent_runs(
        engine,
        AgentRunListFilters(
            operator_review_status=filters.operator_review_status,
            worker_status=filters.worker_status,
            created_from=filters.created_from,
            created_to=filters.created_to,
            cursor=filters.cursor,
            limit=filters.limit,
        ),
    )
    items: list[AgentRunEvaluationItem] = []
    for item in runs.items:
        if filters.run_id is not None and item.run_id != filters.run_id:
            continue
        snapshot_response = await get_review_snapshot(engine, item.run_id)
        snapshot = None if snapshot_response is None else snapshot_response.snapshot
        evaluation = _evaluate_run(item.worker_status, snapshot)
        if (
            filters.parent_handling is not None
            and evaluation.parent_handling != filters.parent_handling
        ):
            continue
        items.append(
            AgentRunEvaluationItem(
                run_id=item.run_id,
                status=item.status,
                alert_id=item.alert_id,
                card_id=item.card_id,
                operator_review_status=item.operator_review_status,
                worker_status=item.worker_status,
                citation_coverage=evaluation.citation_coverage,
                input_validity=evaluation.input_validity,
                parent_handling=evaluation.parent_handling,
                evidence_completeness=evaluation.evidence_completeness,
                review_snapshot_status=item.review_snapshot_status,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )
    return AgentRunEvaluationPage(items=tuple(items), next_cursor=runs.next_cursor)


@dataclass(frozen=True, slots=True)
class EvaluationProjection:
    citation_coverage: CitationCoverage
    input_validity: InputValidity
    parent_handling: ParentHandling
    evidence_completeness: EvidenceCompleteness


def _evaluate_run(
    worker_status: WorkerStatus,
    snapshot: AgentRunReviewSnapshotV1 | None,
) -> EvaluationProjection:
    if snapshot is None:
        return EvaluationProjection(
            citation_coverage="not_applicable",
            input_validity="unavailable",
            parent_handling="unavailable",
            evidence_completeness="missing",
        )
    citation_coverage = _citation_coverage(snapshot)
    return EvaluationProjection(
        citation_coverage=citation_coverage,
        input_validity=_input_validity(worker_status),
        parent_handling=_parent_handling(worker_status, citation_coverage),
        evidence_completeness=_evidence_completeness(snapshot, citation_coverage),
    )


def _citation_coverage(snapshot: AgentRunReviewSnapshotV1) -> CitationCoverage:
    expected_ids: Final = {
        evidence_id
        for hypothesis in snapshot.diagnostic.hypotheses
        for evidence_id in hypothesis.evidence_ids
    }
    if not expected_ids:
        return "not_applicable"
    available_ids = {evidence.evidence_id for evidence in snapshot.evidence}
    covered_count = len(expected_ids & available_ids)
    if covered_count == len(expected_ids):
        return "complete"
    if covered_count > 0:
        return "partial"
    return "missing"


def _input_validity(worker_status: WorkerStatus) -> InputValidity:
    match worker_status:
        case "invalid":
            return "invalid"
        case "not_triggered" | "running":
            return "unavailable"
        case "completed" | "failed" | "timeout" | "budget_exceeded":
            return "valid"


def _parent_handling(
    worker_status: WorkerStatus,
    citation_coverage: CitationCoverage,
) -> ParentHandling:
    match worker_status:
        case "completed":
            if citation_coverage in {"complete", "partial", "not_applicable"}:
                return "used_as_support"
            return "fallback_to_human"
        case "invalid":
            return "invalid"
        case "failed" | "timeout" | "budget_exceeded" | "running":
            return "unavailable"
        case "not_triggered":
            return "fallback_to_human"


def _evidence_completeness(
    snapshot: AgentRunReviewSnapshotV1,
    citation_coverage: CitationCoverage,
) -> EvidenceCompleteness:
    match citation_coverage:
        case "complete":
            return "complete"
        case "partial":
            return "partial"
        case "missing":
            return "missing"
        case "not_applicable":
            if snapshot.evidence:
                return "partial"
            return "missing"
