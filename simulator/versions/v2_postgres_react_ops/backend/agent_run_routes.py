from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from uuid import uuid4

import orjson
from anyio import sleep
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_result_contract import build_ops_agent_result_v4
from agent_execution_repository import AGENT_GRAPH_TASK_KEY_V2
from agent_input_snapshot_repository import get_agent_input_lineage
from agent_loop_repository import list_agent_loop_iterations
from agent_runner import (
    AgentRunRequest,
    SimulateCard,
    is_agent_run_scheduled,
    schedule_reserved_agent_graph,
)
from agent_runtime_factory import create_agent_runtime
from agent_run_artifact_repository import (
    claim_agent_run_action,
    complete_agent_run_action,
    fail_agent_run_action,
    get_agent_run_artifact,
    get_agent_run_artifact_by_id,
    get_effective_output_review_id,
    insert_agent_run_artifact,
    list_agent_run_artifacts,
)
from agent_run_event_repository import (
    AgentRunEventRecord,
    list_agent_run_events_after,
)
from agent_run_repository import (
    AgentRunLineageLimitError,
    get_agent_run,
    record_agent_run_event,
    reserve_agent_run,
)
from alert_repository import get_alert
from heatgrid_ops.agent.contracts import ReportWriteRequest
from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.graph import AgentGraphInvoker
from heatgrid_ops.agent.lineage import source_output_hash
from heatgrid_ops.agent.models import OpsAgentOutput as CoreOpsAgentOutput
from heatgrid_ops.agent.run_models import AutomationPolicySnapshot
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_ops.approval.policy import (
    ActionExecutionContext,
    decide_action_execution,
)
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
from settings import Settings


ROOT = Path(__file__).resolve().parents[4]
REPORT_ROOT = (ROOT / "output" / "ops_agent" / "reports").resolve()


def make_agent_run_router(
    engine: AsyncEngine,
    simulate_card: SimulateCard | None = None,
    runtime: AgentRuntime | None = None,
    graph_provider: Callable[[], AgentGraphInvoker | None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api")
    runtime = runtime or create_agent_runtime(Settings(), engine)

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
        try:
            queued, created = await reserve_agent_run(
                engine,
                run_id=request.run_id,
                alert_id=request.alert_id,
                card_id=request.card_id,
                force_new=payload.force_new,
                requested_by=payload.requested_by,
                reason=payload.reason,
            )
        except AgentRunLineageLimitError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if created or (
            queued.status in {"queued", "running"}
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
                None if graph_provider is None else graph_provider(),
                task_key=AGENT_GRAPH_TASK_KEY_V2,
            )
        return queued

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

    @router.get("/agent-runs/{run_id}/artifacts/{artifact_id}/content")
    async def agent_run_artifact_content(
        run_id: str,
        artifact_id: str,
    ) -> FileResponse:
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
        if not resolved.is_relative_to(REPORT_ROOT) or not resolved.is_file():
            raise HTTPException(status_code=404, detail="artifact file was not found")
        return FileResponse(resolved, filename=artifact.name)

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


async def _create_daily_report_artifact(
    engine: AsyncEngine,
    runtime: AgentRuntime,
    run: AgentRunResponse,
    payload: AgentReportCreateRequest,
) -> AgentRunArtifact:
    if run.ops_output is None:
        raise HTTPException(status_code=409, detail="agent run result is not ready.")
    effective_output = CoreOpsAgentOutput.model_validate(
        run.ops_output.model_dump(mode="json")
    )
    output_hash = source_output_hash(effective_output)
    source_review_id = await get_effective_output_review_id(engine, run.run_id)
    existing = await get_agent_run_artifact(
        engine,
        run_id=run.run_id,
        name="daily_report.json",
        source_output_hash=output_hash,
    )
    policy = AutomationPolicySnapshot.model_validate(
        (await get_automation_policy(engine)).model_dump(mode="json")
    )
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
    lineage = await get_agent_input_lineage(engine, run.run_id)
    if lineage is None or lineage.status != "available" or lineage.source_input is None:
        raise HTTPException(
            status_code=409,
            detail="legacy agent input snapshot is unavailable",
        )
    source_input = lineage.source_input
    external_context = await runtime.external_context_for(run.card_id, source_input)
    action_name = f"daily_report:{output_hash}"
    claimed = await claim_agent_run_action(
        engine,
        run_id=run.run_id,
        action_name=action_name,
        requested_by=payload.requested_by,
    )
    if not claimed:
        for _ in range(100):
            existing = await get_agent_run_artifact(
                engine,
                run_id=run.run_id,
                name="daily_report.json",
                source_output_hash=output_hash,
            )
            if existing is not None:
                return existing
            await sleep(0.05)
        raise HTTPException(status_code=409, detail="daily report generation is already running")

    try:
        draft = await runtime.write_daily(
            ReportWriteRequest(
                run_id=run.run_id,
                card_id=run.card_id,
                source_input=source_input,
                evidence_context=external_context,
                ops_output=effective_output,
                source_output_hash=output_hash,
            )
        )
        artifact = await insert_agent_run_artifact(
            engine,
            run_id=run.run_id,
            kind=draft.kind,
            name=draft.name,
            uri=draft.uri,
            source_output_hash=output_hash,
            source_review_id=source_review_id,
            contract_version="artifact.output-v2",
        )
    except (
        AgentDependencyError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        await fail_agent_run_action(
            engine,
            run_id=run.run_id,
            action_name=action_name,
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
        action_name=action_name,
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
                "source_output_hash": output_hash,
                "source_review_id": source_review_id,
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
        await sleep(poll_interval_seconds)
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
