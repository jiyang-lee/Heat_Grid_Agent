from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.tools import BaseTool

from heatgrid_ops.agent.services import (
    AgentRuntime,
    card_id_from_input as runtime_card_id_from_input,
    fallback_note as runtime_fallback_note,
    generate_note as runtime_generate_note,
    to_json,
)
from heatgrid_rag.search import RagSearcher
from heatgrid_ops.priority.evaluation import (
    ensure_latest_priority_evaluation,
    ensure_priority_evaluation_tables,
)

from agent_run_repository import ensure_agent_run_tables
from agent_loop_repository import ensure_agent_loop_iteration_table
from agent_run_routes import make_agent_run_router
from automation_routes import make_automation_router
from alert_repository import ensure_alert_queue, get_alert
from alert_routes import make_alert_router
from repository import (
    check_database,
    fetch_ops_input,
    list_card_ids,
    list_cards,
    make_engine,
)
from priority_evaluation_routes import make_priority_evaluation_router
from retrain_routes import make_retrain_router
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
from usage import usage_with_totals

settings = Settings()
engine = make_engine(settings.database_url)
rag_searcher = RagSearcher()
agent_runtime = AgentRuntime(settings=settings, rag_searcher=rag_searcher)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
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
    yield


app = FastAPI(title="HeatGrid V2 Local", lifespan=lifespan)
app.include_router(make_alert_router(engine, settings))
app.include_router(make_alert_router(engine, settings, prefix="/api"))
app.include_router(make_priority_evaluation_router(engine, settings))


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
    usage = usage_with_totals(usage, settings)
    return SimulationResponse(
        card_id=card_id,
        input_source="postgresql",
        agent_mode=mode,
        ops_output=output,
        token_usage=usage,
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


def external_context_for(
    card_id: str,
    source_input: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    return agent_runtime.external_context_for(card_id, source_input)


def tools_for(
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue],
) -> list[BaseTool]:
    return agent_runtime.tools_for(source_input, external_context)


async def generate_note(
    card_id: str,
    source_input: dict[str, JsonValue],
) -> tuple[OpsAgentOutput, str, TokenUsage]:
    return await runtime_generate_note(agent_runtime, card_id, source_input)


def fallback_note(
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue] | None = None,
) -> OpsAgentOutput:
    return runtime_fallback_note(source_input, external_context)


async def event_stream(
    card_id: str, source_input: dict[str, JsonValue]
) -> AsyncIterator[str]:
    yield sse("start", f"card_id {card_id} 수신")
    yield sse("input", "PostgreSQL priority_card 조회 완료")
    yield sse("external_context", "세종 매핑, 기상, 운영 참고자료 조회 완료")

    usage = TokenUsage()
    output = fallback_note(source_input)
    async for kind, message, payload, usage, output in agent_runtime.stream_events(
        card_id,
        source_input,
    ):
        yield sse(kind, message, payload)

    usage = usage_with_totals(usage, settings)
    yield sse("token", "토큰 사용량 계산 완료", usage.model_dump(mode="json"))
    yield sse(
        "final",
        "최종 운영 답변 생성 완료",
        {"ops_output": output.model_dump(mode="json"), "token_usage": usage.model_dump()},
    )


def sse(kind: str, message: str, payload: JsonValue | None = None) -> str:
    return f"data: {to_json({'type': kind, 'message': message, 'payload': payload})}\n\n"


app.include_router(make_agent_run_router(engine))
app.include_router(make_automation_router(engine, settings))
app.include_router(make_retrain_router(engine))


if __name__ == "__main__":
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)
