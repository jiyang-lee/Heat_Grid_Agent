from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import orjson
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from openai import OpenAIError
from pydantic import ValidationError

from alert_repository import ensure_alert_queue
from alert_routes import make_alert_router
from repository import (
    check_database,
    fetch_ops_input,
    list_card_ids,
    list_cards,
    make_engine,
)
from schemas import CardSummary, JsonValue, OpsAgentOutput, SimulationResponse, TokenCall, TokenUsage
from settings import SYSTEM_PROMPT, Settings
from usage import usage_with_totals

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR.parent / "frontend"


settings = Settings()
engine = make_engine(settings.database_url)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await ensure_alert_queue(engine)
    yield


app = FastAPI(title="HeatGrid V2 Local", lifespan=lifespan)
app.include_router(make_alert_router(engine))


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/static/{path:path}", include_in_schema=False)
async def static_file(path: str) -> FileResponse:
    return FileResponse(FRONTEND_DIR / "static" / path)


@app.get("/health")
async def health() -> dict[str, str]:
    return {
        "input": "postgresql",
        "database": "connected" if await check_database(engine) else "unavailable",
        "openai": "configured" if settings.openai_api_key is not None else "missing_key",
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
    priority_context = source_input["priority_context"]
    if not isinstance(priority_context, dict):
        raise HTTPException(status_code=500, detail="priority_context 형식 오류")
    card = priority_context["card"]
    if not isinstance(card, dict):
        raise HTTPException(status_code=500, detail="card 형식 오류")
    return str(card["card_id"])


def tools_for(source_input: dict[str, JsonValue]) -> list[BaseTool]:
    @tool
    def get_ops_evidence(card_id: str) -> str:
        """Return card, raw sensor, and ML model evidence from PostgreSQL."""
        if card_id != card_id_from_input(source_input):
            return to_json({"error": "card_id를 찾을 수 없습니다."})
        return to_json(source_input)

    return [get_ops_evidence]


async def generate_note(
    card_id: str,
    source_input: dict[str, JsonValue],
) -> tuple[OpsAgentOutput, Literal["llm", "fallback"], TokenUsage]:
    evidence_payload = tools_for(source_input)[0].invoke({"card_id": card_id})
    usage = TokenUsage(evidence_payload_chars=len(evidence_payload))
    key = settings.openai_api_key
    if key is None:
        return fallback_note(source_input), "fallback", usage

    model = ChatOpenAI(model=settings.openai_model, api_key=key.get_secret_value())
    agent = create_agent(
        model,
        tools_for(source_input),
        system_prompt=SYSTEM_PROMPT,
        response_format=ToolStrategy(OpsAgentOutput),
    )
    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": f"card_id={card_id}"}]}
        )
        return OpsAgentOutput.model_validate(result.get("structured_response")), "llm", usage
    except (OpenAIError, ValidationError):
        return fallback_note(source_input), "fallback", usage


def fallback_note(source_input: dict[str, JsonValue]) -> OpsAgentOutput:
    priority_context = source_input["priority_context"]
    raw_context = source_input["raw_context"]
    if not isinstance(priority_context, dict) or not isinstance(raw_context, dict):
        raise HTTPException(status_code=500, detail="PostgreSQL 입력 형식 오류")
    card = priority_context["card"]
    priority = priority_context["priority"]
    explanation = priority_context["explanation"]
    window = raw_context["window"]
    if not all(isinstance(item, dict) for item in [card, priority, explanation, window]):
        raise HTTPException(status_code=500, detail="PostgreSQL 입력 세부 형식 오류")
    return OpsAgentOutput(
        summary=(
            f"{window['manufacturer_id']} substation {window['substation_id']}에서 "
            f"{priority['priority_level']} priority 카드가 생성됐습니다."
        ),
        action_plan=str(
            explanation.get(
                "recommended_action",
                "priority card, 센서 근거, 모델 근거를 순서대로 확인하세요.",
            )
        ),
        caution="OPENAI_API_KEY가 없거나 LLM 호출에 실패해 로컬 fallback 답변을 사용했습니다.",
    )


async def event_stream(
    card_id: str, source_input: dict[str, JsonValue]
) -> AsyncIterator[str]:
    yield sse("start", f"card_id {card_id} 수신")
    yield sse("input", "PostgreSQL priority_card 조회 완료")

    output = fallback_note(source_input)
    usage = TokenUsage(
        evidence_payload_chars=len(tools_for(source_input)[0].invoke({"card_id": card_id}))
    )
    key = settings.openai_api_key
    if key is None:
        yield sse("fallback", "OPENAI_API_KEY 없음, 로컬 fallback 답변 생성")
    else:
        model = ChatOpenAI(model=settings.openai_model, api_key=key.get_secret_value())
        agent = create_agent(
            model,
            tools_for(source_input),
            system_prompt=SYSTEM_PROMPT,
            response_format=ToolStrategy(OpsAgentOutput),
        )
        try:
            async for event in agent.astream_events(
                {"messages": [{"role": "user", "content": f"card_id={card_id}"}]},
                version="v2",
            ):
                event_name = str(event.get("event", ""))
                run_name = str(event.get("name", ""))
                if event_name == "on_chat_model_start":
                    yield sse("llm", "LLM이 다음 행동을 선택하는 중")
                if event_name == "on_tool_start":
                    yield sse("tool_start", f"{run_name} 호출")
                if event_name == "on_tool_end":
                    yield sse("tool_end", f"{run_name} 결과 관측")
                if event_name == "on_chat_model_end":
                    usage.calls.append(token_call_from_event(event))
                if event_name == "on_chain_end" and run_name == "LangGraph":
                    data = event.get("data", {})
                    result = data.get("output", {}).get("structured_response")
                    output = OpsAgentOutput.model_validate(result)
        except (OpenAIError, ValidationError, KeyError, AttributeError, NotImplementedError):
            yield sse("fallback", "LLM 실행 실패, 로컬 fallback 답변 생성")

    usage = usage_with_totals(usage, settings)
    yield sse("token", "토큰 사용량 계산 완료", usage.model_dump(mode="json"))
    yield sse(
        "final",
        "최종 운영 답변 생성 완료",
        {"ops_output": output.model_dump(mode="json"), "token_usage": usage.model_dump()},
    )


def token_call_from_event(event: dict[str, JsonValue]) -> TokenCall:
    data = event.get("data")
    if not isinstance(data, dict):
        return TokenCall()
    output = data.get("output")
    usage_metadata = getattr(output, "usage_metadata", {}) or {}
    if not isinstance(usage_metadata, dict):
        return TokenCall()
    input_token_details = usage_metadata.get("input_token_details", {})
    cached_input_tokens = 0
    if isinstance(input_token_details, dict):
        cached_input_tokens = int(
            input_token_details.get("cache_read")
            or input_token_details.get("cached_tokens")
            or 0
        )
    return TokenCall(
        input_tokens=int(usage_metadata.get("input_tokens", 0)),
        cached_input_tokens=cached_input_tokens,
        output_tokens=int(usage_metadata.get("output_tokens", 0)),
        total_tokens=int(usage_metadata.get("total_tokens", 0)),
    )



def sse(kind: str, message: str, payload: JsonValue | None = None) -> str:
    return f"data: {to_json({'type': kind, 'message': message, 'payload': payload})}\n\n"


def to_json(payload: JsonValue) -> str:
    return orjson.dumps(payload).decode("utf-8")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
