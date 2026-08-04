from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from operations_report_api_models import ReportType
from operations_report_memo_storage import select_memo
from operations_report_writer import OperationsReportDraft
from schemas import JsonValue


async def build_report_draft(
    connection: AsyncConnection,
    report_type: ReportType,
    period_start: datetime,
    period_end: datetime,
    *,
    generated_at: datetime,
) -> OperationsReportDraft:
    memo = await select_memo(connection, period_start, period_end)
    content: dict[str, JsonValue] = {
        "schema_version": "operations_report.v1",
        "report_type": report_type,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "timezone": "Asia/Seoul",
        "generated_at": generated_at.isoformat(),
        "handover_memo": str(memo["memo"] or "no memo recorded"),
        "source_counts": await snapshot_counts(connection, period_start, period_end),
        "data_quality_caveats": ["repair outcome is not inferred from available data"],
    }
    return OperationsReportDraft(report_type, period_start, period_end, generated_at, content)


async def snapshot_counts(
    connection: AsyncConnection,
    period_start: datetime,
    period_end: datetime,
) -> dict[str, JsonValue]:
    result = await connection.execute(
        text(
            "SELECT "
            "COUNT(*) FILTER (WHERE alerts.status = 'open') AS open_incidents, "
            "COUNT(*) FILTER (WHERE alerts.status = 'resolved') AS resolved_incidents, "
            "COUNT(*) FILTER (WHERE alerts.freshness_status IN "
            "('stale', 'missing', 'failed')) AS data_quality_issues "
            "FROM ops_alert_queue alerts WHERE alerts.created_at >= :period_start "
            "AND alerts.created_at < :period_end"
        ),
        {"period_start": period_start, "period_end": period_end},
    )
    alert_counts = result.mappings().one()
    work_orders = await connection.scalar(
        text(
            "SELECT COUNT(*) FROM agent_runs runs WHERE runs.status = 'completed' "
            "AND runs.created_at >= :period_start AND runs.created_at < :period_end"
        ),
        {"period_start": period_start, "period_end": period_end},
    )
    artifacts = await connection.scalar(
        text(
            "SELECT COUNT(*) FROM agent_run_artifacts artifacts "
            "WHERE artifacts.kind IN ('anomaly_report', 'daily_report') "
            "AND artifacts.created_at >= :period_start AND artifacts.created_at < :period_end"
        ),
        {"period_start": period_start, "period_end": period_end},
    )
    return {
        "open_incidents": int(alert_counts["open_incidents"] or 0),
        "resolved_incidents": int(alert_counts["resolved_incidents"] or 0),
        "data_quality_issues": int(alert_counts["data_quality_issues"] or 0),
        "approved_outcome_unknown_work_orders": int(work_orders or 0),
        "agent_report_artifacts": int(artifacts or 0),
    }
