from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_review_api_models import AgentOperationsMetricsResponse


@dataclass(frozen=True, slots=True)
class AgentOperationsMetricFilters:
    created_from: datetime | None = None
    created_to: datetime | None = None


async def get_agent_operations_metrics(
    engine: AsyncEngine,
    filters: AgentOperationsMetricFilters,
) -> AgentOperationsMetricsResponse:
    where = ["TRUE"]
    params: dict[str, datetime] = {}
    if filters.created_from is not None:
        where.append("runs.created_at >= :created_from")
        params["created_from"] = filters.created_from
    if filters.created_to is not None:
        where.append("runs.created_at <= :created_to")
        params["created_to"] = filters.created_to
    async with engine.connect() as connection:
        run_result = await connection.execute(
            text(
                "SELECT "
                "count(*) AS run_count, "
                "count(*) FILTER (WHERE latest_review.decision IS NULL) "
                "AS pending_review_count, "
                "count(*) FILTER (WHERE latest_review.decision = 'approve') "
                "AS approved_review_count, "
                "count(*) FILTER (WHERE latest_review.decision = 'correct') "
                "AS corrected_review_count, "
                "count(*) FILTER (WHERE latest_review.decision = 'keep_human_review') "
                "AS keep_human_review_count, "
                # worker.worker_status로 한정 — diagnostic_event.worker_status와
                # 이름이 겹쳐 bare 참조는 Postgres에서 ambiguous 오류가 난다.
                "count(*) FILTER (WHERE worker.worker_status = 'completed') "
                "AS diagnostic_completed_count, "
                "count(*) FILTER (WHERE worker.worker_status = 'timeout') "
                "AS diagnostic_timeout_count, "
                "count(*) FILTER (WHERE worker.worker_status = 'invalid') "
                "AS diagnostic_invalid_count, "
                "count(*) FILTER (WHERE worker.worker_status = 'budget_exceeded') "
                "AS diagnostic_budget_exceeded_count "
                "FROM agent_runs runs "
                "LEFT JOIN LATERAL ("
                "SELECT reviews.decision FROM agent_run_reviews reviews "
                "WHERE reviews.run_id = runs.run_id "
                "ORDER BY reviews.review_version DESC LIMIT 1"
                ") latest_review ON TRUE "
                "LEFT JOIN LATERAL ("
                "SELECT events.payload ->> 'status' AS worker_status "
                "FROM agent_run_events events WHERE events.run_id = runs.run_id "
                "AND events.event_type = 'diagnostic_worker_completed' "
                "ORDER BY events.event_id DESC LIMIT 1"
                ") diagnostic_event ON TRUE "
                "LEFT JOIN agent_run_review_snapshots snapshot "
                "ON snapshot.run_id = runs.run_id "
                "CROSS JOIN LATERAL (SELECT CASE "
                "WHEN snapshot.snapshot -> 'diagnostic' ->> 'status' IS NOT NULL "
                "THEN snapshot.snapshot -> 'diagnostic' ->> 'status' "
                "ELSE diagnostic_event.worker_status END AS worker_status"
                ") worker "
                f"WHERE {' AND '.join(where)}"
            ),
            params,
        )
        candidate_result = await connection.execute(
            text(
                "SELECT "
                "count(*) FILTER (WHERE status = 'pending') AS pending, "
                "count(*) FILTER (WHERE status = 'approved') AS approved, "
                "count(*) FILTER (WHERE status = 'rejected') AS rejected "
                "FROM agent_policy_candidates"
            )
        )
    run_row = run_result.mappings().one()
    candidate_row = candidate_result.mappings().one()
    run_count = int(run_row["run_count"])
    approved_count = int(run_row["approved_review_count"])
    corrected_count = int(run_row["corrected_review_count"])
    reviewed_count = (
        approved_count
        + corrected_count
        + int(run_row["keep_human_review_count"])
    )
    return AgentOperationsMetricsResponse(
        run_count=run_count,
        pending_review_count=int(run_row["pending_review_count"]),
        approved_review_count=approved_count,
        corrected_review_count=corrected_count,
        keep_human_review_count=int(run_row["keep_human_review_count"]),
        diagnostic_completed_count=int(run_row["diagnostic_completed_count"]),
        diagnostic_timeout_count=int(run_row["diagnostic_timeout_count"]),
        diagnostic_invalid_count=int(run_row["diagnostic_invalid_count"]),
        diagnostic_budget_exceeded_count=int(
            run_row["diagnostic_budget_exceeded_count"]
        ),
        policy_candidate_pending_count=int(candidate_row["pending"]),
        policy_candidate_approved_count=int(candidate_row["approved"]),
        policy_candidate_rejected_count=int(candidate_row["rejected"]),
        approval_rate=round(approved_count / max(1, reviewed_count), 4),
        correction_rate=round(corrected_count / max(1, reviewed_count), 4),
    )
