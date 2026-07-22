from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final
from uuid import UUID

import orjson
from sqlalchemy import text
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_review_api_models import (
    AgentRunListItem,
    AgentRunListPage,
    OperatorReviewStatus,
    WorkerStatus,
)


LIST_LIMIT_DEFAULT: Final = 50
LIST_LIMIT_MAX: Final = 100


@dataclass(frozen=True, slots=True)
class AgentRunCursorError(ValueError):
    cursor: str

    def __str__(self) -> str:
        return "agent run cursor is malformed"


@dataclass(frozen=True, slots=True)
class AgentRunCursor:
    created_at: datetime
    run_id: str

    def encode(self) -> str:
        payload = orjson.dumps(
            {
                "created_at": self.created_at.astimezone(UTC).isoformat(),
                "run_id": str(UUID(self.run_id)),
            },
            option=orjson.OPT_SORT_KEYS,
        )
        return urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @classmethod
    def decode(cls, cursor: str) -> AgentRunCursor:
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = orjson.loads(urlsafe_b64decode(cursor + padding))
            if not isinstance(payload, dict) or set(payload) != {
                "created_at",
                "run_id",
            }:
                raise AgentRunCursorError(cursor)
            created_at = datetime.fromisoformat(str(payload["created_at"]))
            if created_at.tzinfo is None:
                raise AgentRunCursorError(cursor)
            run_id = str(UUID(str(payload["run_id"])))
        except (KeyError, TypeError, ValueError, orjson.JSONDecodeError) as exc:
            raise AgentRunCursorError(cursor) from exc
        return cls(created_at=created_at.astimezone(UTC), run_id=run_id)


@dataclass(frozen=True, slots=True)
class AgentRunListFilters:
    status: str | None = None
    operator_review_status: OperatorReviewStatus | None = None
    worker_status: WorkerStatus | None = None
    priority: str | None = None
    substation_id: int | None = None
    search: str | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    cursor: AgentRunCursor | None = None
    limit: int = LIST_LIMIT_DEFAULT


def escape_like(value: str) -> str:
    """ILIKE 패턴 메타문자를 리터럴로 취급하도록 이스케이프."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def list_agent_runs(
    engine: AsyncEngine,
    filters: AgentRunListFilters,
) -> AgentRunListPage:
    where = ["TRUE"]
    page_limit = min(max(filters.limit, 1), LIST_LIMIT_MAX)
    params: dict[str, str | int | datetime] = {
        "limit": page_limit + 1,
    }
    if filters.status is not None:
        where.append("run_status = :run_status")
        params["run_status"] = filters.status
    if filters.operator_review_status is not None:
        where.append("operator_review_status = :operator_review_status")
        params["operator_review_status"] = filters.operator_review_status
    if filters.worker_status is not None:
        where.append("worker_status = :worker_status")
        params["worker_status"] = filters.worker_status
    if filters.priority is not None:
        where.append("priority = :priority")
        params["priority"] = filters.priority
    if filters.substation_id is not None:
        where.append("substation_id = :substation_id")
        params["substation_id"] = filters.substation_id
    if filters.search is not None:
        where.append(
            "(alert_reason ILIKE :search OR manufacturer_id ILIKE :search "
            "OR CAST(run_id AS text) ILIKE :search "
            "OR CAST(card_id AS text) ILIKE :search "
            "OR latest_report_name ILIKE :search)"
        )
        params["search"] = f"%{escape_like(filters.search)}%"
    if filters.created_from is not None:
        where.append("created_at >= :created_from")
        params["created_from"] = filters.created_from
    if filters.created_to is not None:
        where.append("created_at <= :created_to")
        params["created_to"] = filters.created_to
    # total_count는 cursor 조건을 제외한 필터 전체 건수(페이지 이동해도 불변).
    count_where = list(where)
    if filters.cursor is not None:
        where.append(
            "(created_at, run_id) < (:cursor_created_at, CAST(:cursor_run_id AS uuid))"
        )
        params["cursor_created_at"] = filters.cursor.created_at
        params["cursor_run_id"] = filters.cursor.run_id

    query = text(
        f"{_LIST_SOURCE_SQL} WHERE {' AND '.join(where)} "
        "ORDER BY created_at DESC, run_id DESC LIMIT :limit"
    )
    count_query = text(
        f"SELECT COUNT(*) AS total FROM ({_LIST_SOURCE_SQL} "
        f"WHERE {' AND '.join(count_where)}) counted"
    )
    count_params = {
        key: value
        for key, value in params.items()
        if key not in {"limit", "cursor_created_at", "cursor_run_id"}
    }
    async with engine.connect() as connection:
        result = await connection.execute(query, params)
        count_result = await connection.execute(count_query, count_params)
    rows = list(result.mappings().all())
    total_count = int(count_result.scalar_one())
    page_rows = rows[:page_limit]
    next_cursor = None
    if len(rows) > page_limit and page_rows:
        last = page_rows[-1]
        next_cursor = AgentRunCursor(
            created_at=last["created_at"],
            run_id=str(last["run_id"]),
        ).encode()
    return AgentRunListPage(
        items=tuple(_list_item(row) for row in page_rows),
        next_cursor=next_cursor,
        total_count=total_count,
    )


def _list_item(row: RowMapping) -> AgentRunListItem:
    return AgentRunListItem(
        run_id=str(row["run_id"]),
        status=row["run_status"],
        alert_id=str(row["alert_id"]),
        card_id=str(row["card_id"]),
        priority=row["priority"],
        operator_review_status=row["operator_review_status"],
        worker_status=row["worker_status"],
        review_snapshot_status=row["review_snapshot_status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        manufacturer_id=row["manufacturer_id"],
        substation_id=row["substation_id"],
        substation_uid=None
        if row["substation_uid"] is None
        else str(row["substation_uid"]),
        alert_reason=row["alert_reason"],
        current_stage=row["current_stage"],
        has_result=bool(row["has_result"]),
        report_artifact_count=int(row["report_artifact_count"]),
        latest_report_name=row["latest_report_name"],
    )


_LIST_SOURCE_SQL: Final = (
    "SELECT * FROM ("
    "SELECT runs.run_id, runs.status AS run_status, runs.alert_id, runs.card_id, "
    "alerts.priority_level AS priority, CASE latest_review.decision "
    "WHEN 'approve' THEN 'approved' WHEN 'correct' THEN 'corrected' "
    "WHEN 'keep_human_review' THEN 'keep_human_review' ELSE 'pending' "
    "END AS operator_review_status, "
    "CASE "
    "WHEN snapshot.snapshot -> 'diagnostic' ->> 'status' IN ("
    "'not_triggered', 'completed', 'failed', 'timeout', 'invalid', "
    "'budget_exceeded') THEN snapshot.snapshot -> 'diagnostic' ->> 'status' "
    "WHEN diagnostic_event.status IN ("
    "'completed', 'failed', 'timeout', 'invalid', 'budget_exceeded') "
    "THEN diagnostic_event.status "
    "WHEN diagnostic_ledger.ledger_id IS NOT NULL THEN 'running' "
    "ELSE 'not_triggered' END AS worker_status, CASE "
    "WHEN snapshot.run_id IS NOT NULL THEN 'available' "
    "WHEN unavailable.event_id IS NOT NULL THEN 'unavailable' "
    "WHEN runs.status IN ('queued', 'running') THEN 'pending' "
    "WHEN runs.review_snapshot_expected IS TRUE THEN 'unavailable' "
    "ELSE 'legacy_unavailable' END AS review_snapshot_status, "
    "runs.created_at, runs.updated_at, "
    "runs.manufacturer_id, runs.substation_id, runs.substation_uid, "
    "alerts.enqueue_reason AS alert_reason, "
    "latest_stage.stage_name AS current_stage, "
    "(runs.ops_output IS NOT NULL) AS has_result, "
    "COALESCE(report_artifacts.report_count, 0) AS report_artifact_count, "
    "report_artifacts.latest_name AS latest_report_name "
    "FROM agent_runs runs "
    "LEFT JOIN ops_alert_queue alerts ON alerts.alert_id = runs.alert_id "
    "LEFT JOIN agent_run_review_snapshots snapshot ON snapshot.run_id = runs.run_id "
    "LEFT JOIN LATERAL (SELECT reviews.decision FROM agent_run_reviews reviews "
    "WHERE reviews.run_id = runs.run_id ORDER BY reviews.review_version DESC LIMIT 1"
    ") latest_review ON TRUE "
    "LEFT JOIN LATERAL (SELECT stages.stage_name FROM agent_stage_snapshots stages "
    "WHERE stages.run_id = runs.run_id "
    "ORDER BY stages.created_at DESC, stages.attempt DESC LIMIT 1"
    ") latest_stage ON TRUE "
    "LEFT JOIN LATERAL (SELECT COUNT(*) AS report_count, "
    "(ARRAY_AGG(reports.name ORDER BY reports.created_at DESC))[1] AS latest_name "
    "FROM agent_run_artifacts reports WHERE reports.run_id = runs.run_id "
    "AND reports.kind IN ('anomaly_report', 'daily_report')"
    ") report_artifacts ON TRUE "
    "LEFT JOIN LATERAL (SELECT events.payload ->> 'status' AS status "
    "FROM agent_run_events events WHERE events.run_id = runs.run_id "
    "AND events.event_type = 'diagnostic_worker_completed' "
    "ORDER BY events.event_id DESC LIMIT 1) diagnostic_event ON TRUE "
    "LEFT JOIN agent_budget_ledger diagnostic_ledger "
    "ON diagnostic_ledger.operation_key = "
    "'diagnostic-budget:' || runs.run_id::text || ':fault_diagnosis:v1' "
    "LEFT JOIN LATERAL (SELECT events.event_id FROM agent_run_events events "
    "WHERE events.run_id = runs.run_id "
    "AND events.event_type = 'review_snapshot_unavailable' "
    "ORDER BY events.event_id DESC LIMIT 1) unavailable ON TRUE) listed"
)
