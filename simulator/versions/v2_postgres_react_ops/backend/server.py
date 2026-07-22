from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.tools import BaseTool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from agent_error_mapping import install_agent_error_handlers
from agent_graph_v2 import build_agent_graph_v2
from agent_runner import resume_reclaimable_agent_runs
from agent_runtime_factory import create_agent_graph_context, create_agent_runtime
from heatgrid_ops.agent.graph import AgentGraphInvoker, build_agent_graph
from heatgrid_ops.agent.helpers import (
    card_id_from_input as runtime_card_id_from_input,
    fallback_note as runtime_fallback_note,
    to_json,
)
from heatgrid_ops.agent.services import generate_note as runtime_generate_note
from heatgrid_ops.agent.tools import make_operational_tools
from heatgrid_ops.agent.models import (
    OpsAgentOutput as CoreOpsAgentOutput,
    TokenUsage as CoreTokenUsage,
)
from heatgrid_ops.agent.usage import usage_with_totals as core_usage_with_totals
from heatgrid_ops.db.migrations import verify_database_contract
from heatgrid_rag.search import RagSearcher
from heatgrid_ops.priority.evaluation import (
    ensure_latest_priority_evaluation,
    ensure_priority_evaluation_tables,
)

from agent_run_repository import ensure_agent_run_tables
from agent_loop_repository import ensure_agent_loop_iteration_table
from agent_run_routes import make_agent_run_router
from agent_review_routes import make_agent_review_router
from agent_quality_routes import make_agent_quality_router
from review_chat_routes import make_review_chat_router
from report_review_routes import make_report_review_router
from automation_routes import make_automation_router
from alert_repository import ensure_alert_queue, get_alert
from alert_routes import make_alert_router
from repository import (
    check_database,
    fetch_ops_input,
    list_card_ids as list_card_ids,
    list_cards,
    make_engine,
)
from priority_evaluation_routes import make_priority_evaluation_router
from operations_policy_repository import (
    PostgresOperationsPolicyRepository,
    verify_operations_policy,
)
from operations_policy_routes import make_operations_policy_router
from operations_report_repository import PostgresOperationsReportRepository
from operations_report_routes import make_operations_report_router
from operations_report_scheduler import OperationsReportScheduler
from replay_routes import make_replay_router
from retrain_routes import make_retrain_router
from demo_ai_history_routes import make_demo_ai_history_router
from retrain_repository import ensure_retrain_tables
from review_repository import ensure_review_tables
from schemas import (
    ApiMetadata,
    CardSummary,
    JsonValue,
    OpsAgentOutput,
    SimulationResponse,
    TokenUsage,
)
from settings import Settings

settings = Settings()
engine = make_engine(settings.database_url)
rag_searcher = RagSearcher()
agent_runtime = create_agent_runtime(settings, engine, rag_searcher)
operations_report_repository = PostgresOperationsReportRepository(engine)
operations_report_scheduler = OperationsReportScheduler(operations_report_repository)


@dataclass(slots=True)
class AgentApplicationResources:
    graph_v1: AgentGraphInvoker | None = None
    graph_v2: AgentGraphInvoker | None = None
    checkpoint_pool: AsyncConnectionPool[AsyncConnection[DictRow]] | None = None


agent_resources = AgentApplicationResources()


def _agent_graph() -> AgentGraphInvoker | None:
    return agent_resources.graph_v2


def _psycopg_database_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await verify_database_contract(settings.database_url)
    await ensure_priority_evaluation_tables(engine)
    await ensure_latest_priority_evaluation(
        engine,
        stale_after_hours=settings.priority_stale_after_hours,
        model_version=settings.priority_model_version,
        expected_substations=settings.priority_expected_substations,
    )
    await ensure_alert_queue(engine)
    await ensure_agent_run_tables(engine)
    await ensure_agent_loop_iteration_table(engine)
    await ensure_review_tables(engine)
    await ensure_retrain_tables(engine)
    await verify_operations_policy(engine)
    await operations_report_repository.ensure_runtime_tables()
    await operations_report_scheduler.run_due_reports(now=datetime.now(UTC))
    checkpoint_pool: AsyncConnectionPool[AsyncConnection[DictRow]] = AsyncConnectionPool(
        conninfo=_psycopg_database_url(settings.database_url),
        min_size=1,
        max_size=10,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )
    await checkpoint_pool.open()
    try:
        checkpointer = AsyncPostgresSaver(checkpoint_pool)
        context = create_agent_graph_context(engine, agent_runtime)
        graph_v1 = build_agent_graph(context, checkpointer=checkpointer)
        graph_v2 = build_agent_graph_v2(
            graph_v1,
            engine,
            openai_model=settings.integrated_agent_model,
            rag_quality_enabled=settings.rag_quality_enabled,
            evidence_threshold=settings.agent_evidence_threshold,
            model_score_tolerance=settings.model_score_tolerance,
            checkpointer=checkpointer,
            runtime=agent_runtime,
        )
        agent_resources.graph_v1 = graph_v1
        agent_resources.graph_v2 = graph_v2
        agent_resources.checkpoint_pool = checkpoint_pool
        await resume_reclaimable_agent_runs(
            engine,
            runtime=agent_runtime,
            graph=graph_v1,
            v2_graph=graph_v2,
        )
        yield
    finally:
        agent_resources.graph_v1 = None
        agent_resources.graph_v2 = None
        agent_resources.checkpoint_pool = None
        await checkpoint_pool.close()


app = FastAPI(title="HeatGrid V2 Local", lifespan=lifespan)
install_agent_error_handlers(app)
app.include_router(make_alert_router(engine, settings))
app.include_router(make_alert_router(engine, settings, prefix="/api"))
app.include_router(make_priority_evaluation_router(engine, settings))
app.include_router(
    make_operations_policy_router(PostgresOperationsPolicyRepository(engine))
)
app.include_router(
    make_operations_report_router(
        operations_report_repository,
        operations_report_scheduler,
    )
)
app.include_router(
    make_replay_router(
        engine,
        storage_root=settings.replay_storage_root,
        replay_enabled=settings.replay_enabled,
        replay_import_enabled=settings.replay_import_enabled,
    )
)


@app.get("/", include_in_schema=False)
async def index() -> ApiMetadata:
    return ApiMetadata(
        service="HeatGrid V2 API",
        health="/health",
        docs="/docs",
        apis=[
            "/api/alerts",
            "/api/priority-evaluations/latest",
            "/api/agent-runs",
            "/api/review-tasks",
            "/api/evidence-candidates",
            "/api/retrain-jobs",
            "/api/model-candidates",
        ],
    )


@app.get("/health")
async def health() -> dict[str, str]:
    rag_health = rag_searcher.health()
    return {
        "input": "postgresql",
        "database": "connected" if await check_database(engine) else "unavailable",
        "openai": "configured" if settings.openai_api_key is not None else "missing_key",
        "rag": str(rag_health.get("active_backend") or rag_health.get("status")),
    }


@app.get("/api/agent-models")
async def agent_models() -> dict[str, str]:
    return {
        "action_plan": settings.integrated_agent_model,
        "work_order": settings.work_order_model,
        "review_chat": settings.natural_chat_model,
        "report": settings.report_model,
    }


@app.get("/cards", response_model=list[CardSummary])
async def cards(
    search: str | None = None,
    priority_level: str | None = None,
) -> list[CardSummary]:
    rows = await list_cards(engine, search=search, priority_level=priority_level)
    return [CardSummary.model_validate(row) for row in rows]


@app.get("/cards/{card_id}/evidence", response_model=None)
async def card_evidence(card_id: str) -> dict[str, JsonValue]:
    source_input = await input_for_card(card_id)
    return {
        "card_id": card_id,
        "data": source_input,
    }


@app.post("/simulate/{card_id}", response_model=SimulationResponse)
async def simulate(card_id: str) -> SimulationResponse:
    source_input = await input_for_card(card_id)
    output, mode, usage = await generate_note(card_id, source_input)
    usage = core_usage_with_totals(usage, agent_runtime.config)
    return SimulationResponse(
        card_id=card_id,
        input_source="postgresql",
        agent_mode=mode,
        ops_output=OpsAgentOutput.model_validate(output.model_dump(mode="json")),
        token_usage=TokenUsage.model_validate(usage.model_dump(mode="json")),
    )


@app.post("/alerts/{alert_id}/simulate", response_model=SimulationResponse)
async def simulate_alert(alert_id: str) -> SimulationResponse:
    alert = await get_alert(engine, alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail="alert_id를 찾을 수 없습니다.")
    return await simulate(str(alert["card_id"]))


@app.get("/simulate-stream/{card_id}", include_in_schema=False)
async def simulate_stream(card_id: str) -> StreamingResponse:
    source_input = await input_for_card(card_id)
    return StreamingResponse(
        event_stream(card_id, source_input), media_type="text/event-stream"
    )


async def input_for_card(card_id: str) -> dict[str, JsonValue]:
    source_input = await fetch_ops_input(engine, card_id)
    if source_input is None:
        raise HTTPException(status_code=404, detail="card_id를 찾을 수 없습니다.")
    return source_input


def card_id_from_input(source_input: dict[str, JsonValue]) -> str:
    return runtime_card_id_from_input(source_input)


async def external_context_for(
    card_id: str,
    source_input: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    return await agent_runtime.external_context_for(card_id, source_input)


def tools_for(
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue],
) -> list[BaseTool]:
    return make_operational_tools(source_input, external_context)


async def generate_note(
    card_id: str,
    source_input: dict[str, JsonValue],
) -> tuple[CoreOpsAgentOutput, Literal["llm", "fallback"], CoreTokenUsage]:
    return await runtime_generate_note(agent_runtime, card_id, source_input)


def fallback_note(
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue] | None = None,
) -> CoreOpsAgentOutput:
    return runtime_fallback_note(source_input, external_context)


async def event_stream(
    card_id: str, source_input: dict[str, JsonValue]
) -> AsyncIterator[str]:
    yield sse("start", f"card_id {card_id} 수신")
    yield sse("input", "PostgreSQL priority_card 조회 완료")
    yield sse("external_context", "세종 매핑, 기상, 운영 참고자료 조회 완료")

    usage = CoreTokenUsage()
    output = fallback_note(source_input)
    async for kind, message, payload, usage, output in agent_runtime.stream_events(
        card_id,
        source_input,
    ):
        yield sse(kind, message, payload)

    usage = core_usage_with_totals(usage, agent_runtime.config)
    yield sse("token", "토큰 사용량 계산 완료", usage.model_dump(mode="json"))
    yield sse(
        "final",
        "최종 운영 답변 생성 완료",
        {"ops_output": output.model_dump(mode="json"), "token_usage": usage.model_dump()},
    )


def sse(kind: str, message: str, payload: JsonValue | None = None) -> str:
    return f"data: {to_json({'type': kind, 'message': message, 'payload': payload})}\n\n"


app.include_router(make_agent_run_router(engine, runtime=agent_runtime))
app.include_router(make_agent_review_router(engine, settings, agent_runtime, _agent_graph))
app.include_router(make_review_chat_router(engine, settings, agent_runtime, _agent_graph))
app.include_router(make_report_review_router(settings))
app.include_router(make_agent_quality_router(engine))
app.include_router(make_automation_router(engine, settings))
app.include_router(make_retrain_router(engine))
app.include_router(make_demo_ai_history_router(engine, enabled=settings.demo_ai_history_reset_enabled))


if __name__ == "__main__":
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
