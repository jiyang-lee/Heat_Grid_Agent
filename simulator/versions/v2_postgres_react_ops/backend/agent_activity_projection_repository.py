"""AI 활동 페이지용 read-only projection.

작업지시서 = result(ops_output) 보유 agent run projection (별도 테이블 없음).
보고서 = agent_run_artifacts의 report kind(anomaly_report/daily_report) projection.
둘 다 기존 테이블만 조회하며 상태 정본은 latest operator review다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_review_api_models import (
    AgentReportListItem,
    AgentReportListPage,
    OperatorReviewStatus,
    WorkOrderListItem,
    WorkOrderListPage,
)
from agent_run_listing_repository import (
    LIST_LIMIT_DEFAULT,
    LIST_LIMIT_MAX,
    AgentRunCursor,
    escape_like,
)


REPORT_ARTIFACT_KINDS: Final = ("anomaly_report", "daily_report")


@dataclass(frozen=True, slots=True)
class ActivityProjectionFilters:
    operator_review_status: OperatorReviewStatus | None = None
    substation_id: int | None = None
    search: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    cursor: AgentRunCursor | None = None
    limit: int = LIST_LIMIT_DEFAULT


def _build_where(
    filters: ActivityProjectionFilters,
    *,
    search_columns: tuple[str, ...],
    cursor_id_column: str,
) -> tuple[list[str], list[str], dict[str, str | int | datetime]]:
    """공통 WHERE 절 구성. count용(cursor 제외)과 page용을 함께 반환."""
    where = ["TRUE"]
    params: dict[str, str | int | datetime] = {}
    if filters.operator_review_status is not None:
        where.append("operator_review_status = :operator_review_status")
        params["operator_review_status"] = filters.operator_review_status
    if filters.substation_id is not None:
        where.append("substation_id = :substation_id")
        params["substation_id"] = filters.substation_id
    if filters.search is not None:
        predicates = " OR ".join(
            f"{column} ILIKE :search" for column in search_columns
        )
        where.append(f"({predicates})")
        params["search"] = f"%{escape_like(filters.search)}%"
    if filters.created_from is not None:
        where.append("created_at >= :created_from")
        params["created_from"] = filters.created_from
    if filters.created_to is not None:
        where.append("created_at <= :created_to")
        params["created_to"] = filters.created_to
    count_where = list(where)
    if filters.cursor is not None:
        where.append(
            f"(created_at, {cursor_id_column}) < "
            "(:cursor_created_at, CAST(:cursor_id AS uuid))"
        )
        params["cursor_created_at"] = filters.cursor.created_at
        params["cursor_id"] = filters.cursor.run_id
    return where, count_where, params


async def _run_page(
    engine: AsyncEngine,
    *,
    source_sql: str,
    filters: ActivityProjectionFilters,
    search_columns: tuple[str, ...],
    cursor_id_column: str,
) -> tuple[list[RowMapping], str | None, int]:
    page_limit = min(max(filters.limit, 1), LIST_LIMIT_MAX)
    where, count_where, params = _build_where(
        filters,
        search_columns=search_columns,
        cursor_id_column=cursor_id_column,
    )
    query = text(
        f"{source_sql} WHERE {' AND '.join(where)} "
        f"ORDER BY created_at DESC, {cursor_id_column} DESC LIMIT :limit"
    )
    count_query = text(
        f"SELECT COUNT(*) AS total FROM ({source_sql} "
        f"WHERE {' AND '.join(count_where)}) counted"
    )
    count_params = {
        key: value
        for key, value in params.items()
        if key not in {"cursor_created_at", "cursor_id"}
    }
    async with engine.connect() as connection:
        result = await connection.execute(query, {**params, "limit": page_limit + 1})
        count_result = await connection.execute(count_query, count_params)
    rows = list(result.mappings().all())
    total_count = int(count_result.scalar_one())
    page_rows = rows[:page_limit]
    next_cursor = None
    if len(rows) > page_limit and page_rows:
        last = page_rows[-1]
        next_cursor = AgentRunCursor(
            created_at=last["created_at"],
            run_id=str(last[cursor_id_column]),
        ).encode()
    return page_rows, next_cursor, total_count


async def list_work_orders(
    engine: AsyncEngine,
    filters: ActivityProjectionFilters,
) -> WorkOrderListPage:
    page_rows, next_cursor, total_count = await _run_page(
        engine,
        source_sql=_WORK_ORDER_SOURCE_SQL,
        filters=filters,
        search_columns=(
            "alert_reason",
            "manufacturer_id",
            "CAST(run_id AS text)",
        ),
        cursor_id_column="run_id",
    )
    return WorkOrderListPage(
        items=tuple(
            WorkOrderListItem(
                run_id=str(row["run_id"]),
                priority=row["priority"],
                alert_reason=row["alert_reason"],
                manufacturer_id=row["manufacturer_id"],
                substation_id=row["substation_id"],
                substation_uid=None
                if row["substation_uid"] is None
                else str(row["substation_uid"]),
                operator_review_status=row["operator_review_status"],
                created_at=row["created_at"],
            )
            for row in page_rows
        ),
        next_cursor=next_cursor,
        total_count=total_count,
    )


async def list_agent_reports(
    engine: AsyncEngine,
    filters: ActivityProjectionFilters,
) -> AgentReportListPage:
    page_rows, next_cursor, total_count = await _run_page(
        engine,
        source_sql=_REPORT_SOURCE_SQL,
        filters=filters,
        search_columns=(
            "name",
            "alert_reason",
            "manufacturer_id",
            "CAST(run_id AS text)",
        ),
        cursor_id_column="artifact_id",
    )
    return AgentReportListPage(
        items=tuple(
            AgentReportListItem(
                artifact_id=str(row["artifact_id"]),
                run_id=str(row["run_id"]),
                kind=row["kind"],
                name=row["name"],
                uri=row["uri"],
                priority=row["priority"],
                manufacturer_id=row["manufacturer_id"],
                substation_id=row["substation_id"],
                substation_uid=None
                if row["substation_uid"] is None
                else str(row["substation_uid"]),
                operator_review_status=row["operator_review_status"],
                created_at=row["created_at"],
            )
            for row in page_rows
        ),
        next_cursor=next_cursor,
        total_count=total_count,
    )


_LATEST_REVIEW_STATUS_SQL: Final = (
    "CASE latest_review.decision "
    "WHEN 'approve' THEN 'approved' WHEN 'correct' THEN 'corrected' "
    "WHEN 'keep_human_review' THEN 'keep_human_review' ELSE 'pending' "
    "END AS operator_review_status"
)

_WORK_ORDER_SOURCE_SQL: Final = (
    "SELECT * FROM ("
    "SELECT runs.run_id, alerts.priority_level AS priority, "
    "alerts.enqueue_reason AS alert_reason, "
    "runs.manufacturer_id, runs.substation_id, runs.substation_uid, "
    f"{_LATEST_REVIEW_STATUS_SQL}, "
    "runs.created_at FROM agent_runs runs "
    "LEFT JOIN ops_alert_queue alerts ON alerts.alert_id = runs.alert_id "
    "LEFT JOIN LATERAL (SELECT reviews.decision FROM agent_run_reviews reviews "
    "WHERE reviews.run_id = runs.run_id ORDER BY reviews.review_version DESC LIMIT 1"
    ") latest_review ON TRUE "
    "WHERE runs.ops_output IS NOT NULL) work_orders"
)

_REPORT_SOURCE_SQL: Final = (
    "SELECT * FROM ("
    "SELECT artifacts.artifact_id, artifacts.run_id, artifacts.kind, "
    "artifacts.name, artifacts.uri, alerts.priority_level AS priority, "
    "runs.manufacturer_id, runs.substation_id, runs.substation_uid, "
    f"{_LATEST_REVIEW_STATUS_SQL}, "
    "artifacts.created_at FROM agent_run_artifacts artifacts "
    "JOIN agent_runs runs ON runs.run_id = artifacts.run_id "
    "LEFT JOIN ops_alert_queue alerts ON alerts.alert_id = runs.alert_id "
    "LEFT JOIN LATERAL (SELECT reviews.decision FROM agent_run_reviews reviews "
    "WHERE reviews.run_id = runs.run_id ORDER BY reviews.review_version DESC LIMIT 1"
    ") latest_review ON TRUE "
    "WHERE artifacts.kind IN ('anomaly_report', 'daily_report')) report_artifacts"
)
