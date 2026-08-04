from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from pathlib import Path
from uuid import uuid4

import orjson
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from openai import OpenAIError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_result_contract import build_ops_agent_result_v4
from agent_loop_repository import list_agent_loop_iterations
from agent_runner import (
    AgentRunRequest,
    SimulateCard,
    cancel_scheduled_agent_graph,
    is_agent_run_scheduled,
    schedule_reserved_agent_graph,
)
from agent_run_artifact_repository import (
    claim_agent_run_action,
    complete_agent_run_action,
    fail_agent_run_action,
    get_agent_run_artifact,
    get_agent_run_artifact_by_id,
    insert_agent_run_artifact,
    list_agent_run_artifacts,
)
from agent_run_event_repository import (
    AgentRunEventRecord,
    list_agent_run_events_after,
)
from agent_run_repository import (
    cancel_queued_agent_run,
    get_agent_run,
    record_agent_run_event,
    reserve_agent_run,
)
from alert_repository import get_alert
from heatgrid_ops.agent.helpers import to_json
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_ops.agent.tools import ReportToolPayloadError, make_daily_report_tool
from heatgrid_ops.approval.policy import (
    ActionExecutionContext,
    decide_action_execution,
)
from heatgrid_rag.search import RagSearcher
from repository import fetch_ops_input
from review_repository import get_automation_policy
from schemas import (
    AgentReportCreateRequest,
    AgentRunArtifact,
    AgentRunCreateRequest,
    AgentLoopIteration,
    AgentRunResponse,
    OpsAgentResultV4,
    JsonValue,
)
from report_pdf import render_incident_report_pdf
from report_docx import render_anomaly_report_docx
from settings import Settings


ROOT = Path(__file__).resolve().parents[4]
REPORT_ROOT = (ROOT / "output" / "ops_agent" / "reports").resolve()


def make_agent_run_router(
    engine: AsyncEngine,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api")
    runtime = runtime or AgentRuntime(settings=Settings(), rag_searcher=RagSearcher())

    @router.post("/agent-runs", response_model=AgentRunResponse)
    async def create_agent_run(payload: AgentRunCreateRequest) -> AgentRunResponse:
        alert = await get_alert(engine, payload.alert_id)
        if alert is None:
            raise HTTPException(status_code=404, detail="alert_id를 찾을 수 없습니다.")
        if payload.force_new and (payload.requested_by is None or payload.reason is None):
            raise HTTPException(
                status_code=422,
                detail="requested_by and reason are required for a manual rerun.",
            )
        request = AgentRunRequest(
            run_id=str(uuid4()),
            alert_id=payload.alert_id,
            card_id=str(alert["card_id"]),
        )
        queued, created = await reserve_agent_run(
            engine,
            run_id=request.run_id,
            alert_id=request.alert_id,
            card_id=request.card_id,
            force_new=payload.force_new,
            requested_by=payload.requested_by,
            reason=payload.reason,
        )
        if created or (
            queued.status == "queued"
            and not is_agent_run_scheduled(queued.run_id)
        ):
            schedule_reserved_agent_graph(
                engine,
                AgentRunRequest(
                    run_id=queued.run_id,
                    alert_id=queued.alert_id,
                    card_id=queued.card_id,
                ),
                simulate_card,
                runtime,
            )
        return queued

    @router.post("/agent-runs/{run_id}/cancel", response_model=AgentRunResponse)
    async def cancel_agent_run(run_id: str) -> AgentRunResponse:
        cancelled = await cancel_queued_agent_run(engine, run_id)
        if cancelled is not None:
            cancel_scheduled_agent_graph(run_id)
            return cancelled
        existing = await get_agent_run(engine, run_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        raise HTTPException(
            status_code=409,
            detail="대기 중인 AI 조치만 취소할 수 있습니다.",
        )

    @router.get("/agent-runs/{run_id}", response_model=AgentRunResponse)
    async def agent_run(run_id: str) -> AgentRunResponse:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        return run

    @router.get("/agent-runs/{run_id}/result", response_model=OpsAgentResultV4)
    async def agent_run_result(run_id: str) -> OpsAgentResultV4:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        result = build_ops_agent_result_v4(run)
        if result is None:
            raise HTTPException(status_code=409, detail="agent run result is not ready.")
        return result

    @router.get("/agent-runs/{run_id}/artifacts", response_model=list[AgentRunArtifact])
    async def agent_run_artifacts(run_id: str) -> list[AgentRunArtifact]:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        return await list_agent_run_artifacts(engine, run_id)

    @router.get(
        "/agent-runs/{run_id}/artifacts/{artifact_id}/content",
        response_model=None,
    )
    async def agent_run_artifact_content(
        run_id: str,
        artifact_id: str,
    ) -> FileResponse | JSONResponse:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        artifact = await get_agent_run_artifact_by_id(
            engine,
            run_id=run_id,
            artifact_id=artifact_id,
        )
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact_id was not found")
        path = Path(artifact.uri)
        if not path.is_absolute():
            path = ROOT / path
        resolved = path.resolve()
        if resolved.is_relative_to(REPORT_ROOT) and resolved.is_file():
            return FileResponse(resolved, filename=artifact.name)
        if artifact.kind != "anomaly_report":
            raise HTTPException(status_code=404, detail="artifact file was not found")
        return JSONResponse(await _fallback_report_from_run(engine, run))

    @router.get("/agent-runs/{run_id}/artifacts/{artifact_id}/report.docx")
    async def agent_run_artifact_docx(
        run_id: str,
        artifact_id: str,
    ) -> StreamingResponse:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        artifact = await get_agent_run_artifact_by_id(
            engine,
            run_id=run_id,
            artifact_id=artifact_id,
        )
        if artifact is None or artifact.kind != "anomaly_report":
            raise HTTPException(status_code=404, detail="이상 분석 보고서를 찾을 수 없습니다.")
        path = Path(artifact.uri)
        if not path.is_absolute():
            path = ROOT / path
        resolved = path.resolve()
        if resolved.is_relative_to(REPORT_ROOT) and resolved.is_file():
            try:
                report = orjson.loads(await asyncio.to_thread(resolved.read_bytes))
            except orjson.JSONDecodeError as error:
                raise HTTPException(status_code=422, detail="보고서 JSON을 읽을 수 없습니다.") from error
            if not isinstance(report, dict):
                raise HTTPException(status_code=422, detail="보고서 JSON 형식이 올바르지 않습니다.")
        else:
            report = await _fallback_report_from_run(engine, run)
        building_name = await _report_building_name(engine, run.substation_id)
        document = await asyncio.to_thread(
            render_anomaly_report_docx,
            report,
            alert_id=run.alert_id,
            building_name=building_name,
            machine_room=_machine_room_name(run.substation_id),
            status_label=_report_status_label(run.review_status),
            document_version=1,
        )
        filename = f"heatgrid-anomaly-report-{run.substation_id or 'unknown'}.docx"
        return StreamingResponse(
            iter((document,)),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @router.post(
        "/agent-runs/{run_id}/reports/daily",
        response_model=AgentRunArtifact,
    )
    async def create_daily_report(
        run_id: str,
        payload: AgentReportCreateRequest,
    ) -> AgentRunArtifact:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        if run.status != "completed" or run.ops_output is None:
            raise HTTPException(status_code=409, detail="완료된 실행만 보고서를 생성할 수 있습니다.")
        return await _create_daily_report_artifact(
            engine,
            runtime,
            run,
            payload,
        )

    @router.get(
        "/agent-runs/{run_id}/iterations",
        response_model=list[AgentLoopIteration],
    )
    async def agent_run_iterations(run_id: str) -> list[AgentLoopIteration]:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        return await list_agent_loop_iterations(engine, run_id)

    @router.get("/agent-runs/{run_id}/reports/incident.pdf")
    async def incident_report_pdf(run_id: str) -> FileResponse:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        result = build_ops_agent_result_v4(run)
        if result is None:
            raise HTTPException(status_code=409, detail="완료된 작업지시서가 필요합니다.")
        output_path = REPORT_ROOT / run_id / f"incident_report_{result.substation_id or 'unknown'}.pdf"
        await asyncio.to_thread(render_incident_report_pdf, output_path, run=run, result=result)
        return FileResponse(output_path, filename=output_path.name, media_type="application/pdf")

    @router.get("/agent-runs/{run_id}/events")
    async def agent_run_events_response(
        run_id: str,
        after_event_id: int = Query(default=0, ge=0),
    ) -> StreamingResponse:
        run = await get_agent_run(engine, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_id를 찾을 수 없습니다.")
        return StreamingResponse(
            stream_agent_run_events(
                engine,
                run_id,
                after_event_id=after_event_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return router


async def _report_building_name(engine: AsyncEngine, substation_id: int | None) -> str:
    if substation_id is None:
        return "대상 건물 미확인"
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT apartment_name FROM substation_building_context "
                "WHERE substation_id = :substation_id"
            ),
            {"substation_id": substation_id},
        )
    return str(result.scalar_one_or_none() or f"기계실 {substation_id} 대상 건물")


def _machine_room_name(substation_id: int | None) -> str:
    return "기계실" if substation_id is None else f"기계실 {substation_id}"


def _report_status_label(status: str | None) -> str:
    return {
        "approved": "승인 완료",
        "corrected": "교정 기록됨",
        "rejected": "사람 검토 필요",
    }.get(status or "", "검토 대기")


async def _fallback_report_from_run(engine: AsyncEngine, run: AgentRunResponse) -> dict[str, object]:
    result = build_ops_agent_result_v4(run)
    if result is None:
        raise HTTPException(status_code=409, detail="agent run result is not ready.")
    generated_at = run.created_at.isoformat() if run.created_at is not None else ""
    source_input = await fetch_ops_input(engine, run.card_id)
    source_priority = _source_priority(source_input)
    sensor_measurements = _sensor_measurements(source_input)
    loop_summary = run.loop_summary.model_dump(mode="json") if run.loop_summary is not None else {}
    verification = loop_summary.get("model_verification", {})
    verification = verification if isinstance(verification, dict) else {}
    evidence = [
        {
            "label": item.label,
            "value": item.content,
            "interpretation": item.content,
            "confidence": "분석 실행 결과",
            "evidence_ref_ids": [f"result-evidence-{index}"],
        }
        for index, item in enumerate(result.evidence, start=1)
    ]
    references = [
        {
            "ref_id": f"result-evidence-{index}",
            "source_type": item.source,
            "title": item.label,
            "excerpt": item.content,
        }
        for index, item in enumerate(result.evidence, start=1)
    ]
    actions = _action_items(result)
    summary = _report_sentence(result.situation)
    return {
        "report_metadata": {
            "report_id": f"HG-{run.substation_id or 'NA'}-{run.run_id[:8]}",
            "generated_at": generated_at,
            "source_card_id": result.card_id,
        },
        "target_asset": {
            "asset_label": _machine_room_name(run.substation_id),
            "configuration_type": "원 실행 결과에서 설비 계통 확인 필요",
            "window_start": "",
            "window_end": "",
        },
        "priority_summary": {
            "priority_level": source_priority.get("priority_level") or "확인 필요",
            "priority_score": source_priority.get("priority_score") or "확인 필요",
            "confidence": verification.get("confidence") or "분석 실행 결과",
            "urgency": source_priority.get("predicted_lead_time_bucket") or "운영자 검토 필요",
            "operator_review": _report_status_label(run.review_status),
            "priority_reason": _report_sentence(source_priority.get("why_reason") or result.situation),
        },
        "situation_summary": {
            "headline": result.headline,
            "summary": summary,
            "current_status": _report_status_label(run.review_status),
            "impact_summary": _report_sentence(result.headline),
        },
        "sensor_measurements": sensor_measurements,
        "model_judgment": {
            "anomaly_score": verification.get("anomaly_score") or source_priority.get("anomaly_ensemble_score") or "확인 필요",
            "anomaly_label": verification.get("anomaly_label") or source_priority.get("operational_label") or "확인 필요",
            "m1_specialist_priority_score": verification.get("m1_specialist_priority_score") or source_priority.get("m1_specialist_priority_score") or "확인 필요",
            "agreement": verification.get("agreement") or source_priority.get("m1_priority_agreement") or "확인 필요",
            "reason": _report_sentence((verification.get("reasons") or [None])[0] or result.situation),
        },
        "key_evidence": evidence,
        "risk_analysis": {
            "risk_level": source_priority.get("risk_level_calibrated") or "확인 필요",
            "risk_score": source_priority.get("risk_score") or "확인 필요",
            "risk_summary": summary,
            "operational_impact": _report_sentence(result.headline),
        },
        "recommended_actions": actions,
        "evidence_references": references,
        "operator_note": {
            "note": "\n".join(_report_sentence(item) for item in result.cautions),
            "review_reasons": [],
        },
        "rendering_hints": {"display_title": "AI 이상 분석 보고서"},
    }


def _source_priority(source_input: object) -> dict[str, object]:
    if not isinstance(source_input, dict):
        return {}
    sections = source_input.get("sections")
    priority = sections.get("priority") if isinstance(sections, dict) else None
    card = priority.get("priority_card") if isinstance(priority, dict) else None
    raw = card.get("raw_card") if isinstance(card, dict) else None
    return raw if isinstance(raw, dict) else card if isinstance(card, dict) else {}


def _sensor_measurements(source_input: object) -> list[dict[str, object]]:
    if not isinstance(source_input, dict):
        return []
    sections = source_input.get("sections")
    rows = sections.get("sensor_summaries") if isinstance(sections, dict) else None
    if not isinstance(rows, list):
        return []
    labels = {"supply_temp": "공급 온도", "return_temp": "환수 온도", "flow": "유량", "pressure": "차압", "delta_t": "온도차 ΔT"}
    measurements: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        feature = str(row.get("feature_name") or "").lower()
        label = next((value for key, value in labels.items() if key in feature), None)
        if label is None:
            continue
        measurements.append({"label": label, "current_value": row.get("feature_value"), "data_status": "분석 특성 확인됨", "judgement": row.get("meaning") or "분석 특성으로 확인됨"})
    return measurements


def _action_items(result) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for action in result.actions:
        detail = _report_sentence(action.detail)
        parts = [part.strip() for part in re.split(r"(?:(?<=\n)|(?<=\.)\s+)(?=\d+[.)]\s)", detail) if part.strip()]
        for part in parts or [detail]:
            items.append({"action": f"{action.title}: {part}", "urgency": f"우선순위 {action.priority}", "owner_hint": "운영 담당자"})
    return items


def _report_sentence(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"제공된 카드\([^)]*\)는\s*", "분석 대상은 ", text)
    text = re.sub(r"\([^)]*card[^)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*#{1,6}\s*", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+(?=\d+[.)]\s)", "\n", text)


async def _create_daily_report_artifact(
    engine: AsyncEngine,
    runtime: AgentRuntime,
    run: AgentRunResponse,
    payload: AgentReportCreateRequest,
) -> AgentRunArtifact:
    existing = await get_agent_run_artifact(
        engine,
        run_id=run.run_id,
        name="daily_report.json",
    )
    policy = await get_automation_policy(engine)
    execution = decide_action_execution(
        policy,
        ActionExecutionContext(
            task_type="daily_report",
            risk_level="low",
            confidence=1.0,
            source_trust=1.0,
            explicit_user_command=True,
            already_executed=existing is not None,
            used_count=0,
            max_count=1,
        ),
    )
    await record_agent_run_event(
        engine,
        AgentRunEventRecord(
            run_id=run.run_id,
            event_type="action_policy_decision",
            message=f"daily report policy: {execution.action}",
            payload={
                "task_type": "daily_report",
                "action": execution.action,
                "reason": execution.reason,
                "requested_by": payload.requested_by,
            },
        ),
    )
    if execution.action == "reuse" and existing is not None:
        return existing
    if execution.action != "execute":
        raise HTTPException(status_code=409, detail=execution.reason)

    key = runtime.settings.openai_api_key
    if key is None:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY가 필요합니다.")
    source_input = await fetch_ops_input(engine, run.card_id)
    if source_input is None:
        raise HTTPException(status_code=404, detail="card_id를 찾을 수 없습니다.")
    external_context = runtime.external_context_for(run.card_id, source_input)
    claimed = await claim_agent_run_action(
        engine,
        run_id=run.run_id,
        action_name="daily_report",
        requested_by=payload.requested_by,
    )
    if not claimed:
        for _ in range(100):
            existing = await get_agent_run_artifact(
                engine,
                run_id=run.run_id,
                name="daily_report.json",
            )
            if existing is not None:
                return existing
            await asyncio.sleep(0.05)
        raise HTTPException(status_code=409, detail="daily report generation is already running")

    report_tool = make_daily_report_tool(
        openai_api_key=key.get_secret_value(),
        openai_model=runtime.settings.openai_model,
    )
    try:
        tool_result = await asyncio.to_thread(
            report_tool.invoke,
            {
                "payload_json": to_json(
                    {
                        "run_id": run.run_id,
                        "card_id": run.card_id,
                        "source_input": source_input,
                        "external_context": external_context,
                        "ops_output": run.ops_output.model_dump(mode="json"),
                    }
                )
            },
        )
        artifact_payload = _json_object(tool_result)
        artifact = await insert_agent_run_artifact(
            engine,
            run_id=run.run_id,
            kind=_required_text(artifact_payload, "kind"),
            name=_required_text(artifact_payload, "name"),
            uri=_required_text(artifact_payload, "uri"),
        )
    except (
        OSError,
        RuntimeError,
        ValueError,
        OpenAIError,
        ReportToolPayloadError,
    ) as exc:
        await fail_agent_run_action(
            engine,
            run_id=run.run_id,
            action_name="daily_report",
            error=str(exc),
        )
        await record_agent_run_event(
            engine,
            AgentRunEventRecord(
                run_id=run.run_id,
                event_type="report_failed",
                message="daily report failed",
                payload={"kind": "daily_report", "error": str(exc)[:500]},
            ),
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    await complete_agent_run_action(
        engine,
        run_id=run.run_id,
        action_name="daily_report",
        artifact_id=artifact.artifact_id,
    )

    await record_agent_run_event(
        engine,
        AgentRunEventRecord(
            run_id=run.run_id,
            event_type="report_written",
            message="daily report written",
            payload={
                "kind": artifact.kind,
                "name": artifact.name,
                "uri": artifact.uri,
                "requested_by": payload.requested_by,
            },
        ),
    )
    return artifact


async def stream_agent_run_events(
    engine: AsyncEngine,
    run_id: str,
    *,
    after_event_id: int = 0,
    poll_interval_seconds: float = 0.25,
) -> AsyncIterator[str]:
    last_event_id = after_event_id
    idle_seconds = 0.0
    while True:
        events = await list_agent_run_events_after(
            engine,
            run_id,
            after_event_id=last_event_id,
        )
        for event in events:
            last_event_id = event.event_id
            idle_seconds = 0.0
            yield sse(
                event.event_type,
                event.message,
                event.payload,
                event_id=event.event_id,
            )
        run = await get_agent_run(engine, run_id)
        if run is None or (run.status in {"completed", "failed"} and not events):
            break
        await asyncio.sleep(poll_interval_seconds)
        idle_seconds += poll_interval_seconds
        if idle_seconds >= 15.0:
            idle_seconds = 0.0
            yield ": heartbeat\n\n"


def sse(
    kind: str,
    message: str,
    payload: JsonValue | None = None,
    *,
    event_id: int | None = None,
) -> str:
    event = {"type": kind, "message": message, "payload": payload}
    prefix = "" if event_id is None else f"id: {event_id}\n"
    return f"{prefix}data: {orjson.dumps(event).decode('utf-8')}\n\n"


def _json_object(payload: str) -> dict[str, JsonValue]:
    value = orjson.loads(payload)
    if not isinstance(value, dict):
        raise ReportToolPayloadError("tool result must be a JSON object")
    return value


def _required_text(payload: dict[str, JsonValue], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise ReportToolPayloadError(f"{field_name} must be a non-empty string")
    return value
