from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from heat_grid_ops.llm_input import build_ops_agent_llm_input
from heat_grid_ops.openai_ops import generate_ops_note
from heat_grid_ops.repository import (
    check_database,
    fetch_ops_input,
    list_card_ids,
    load_example_input,
    make_engine,
    save_ops_note,
    setup_database,
)
from heat_grid_ops.schemas import (
    HealthResponse,
    OpsAgentInput,
    OpsAgentLlmInput,
    OpsAgentOutput,
    SimulationResponse,
    StatusResponse,
)
from heat_grid_ops.settings import get_settings

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    app = FastAPI(title="HeatGrid Ops Simulation")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        database = "connected" if await check_database(engine) else "unavailable"
        openai = "configured" if settings.openai_api_key is not None else "missing_key"
        return HealthResponse(database=database, openai=openai)

    @app.post("/api/db/init")
    async def init_db() -> StatusResponse:
        try:
            await setup_database(engine)
        except (SQLAlchemyError, OSError) as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        return StatusResponse(status="initialized")

    @app.get("/api/cards", response_model=list[str])
    async def cards() -> list[str]:
        try:
            return await list_card_ids(engine)
        except (SQLAlchemyError, OSError):
            return [load_example_input().priority_context.card.card_id]

    @app.get("/api/input/{card_id}", response_model=OpsAgentLlmInput)
    async def ops_input(card_id: str) -> OpsAgentLlmInput:
        return build_ops_agent_llm_input(await _input_for_card(engine, card_id))

    @app.post("/api/simulate/{card_id}", response_model=SimulationResponse)
    async def simulate(card_id: str) -> SimulationResponse:
        source_payload = await _input_for_card(engine, card_id)
        input_source = _source_for_card(source_payload, card_id)
        ops_payload = build_ops_agent_llm_input(source_payload)
        output = await generate_ops_note(ops_payload, settings)
        saved = await _save_if_possible(engine, ops_payload, output)
        return SimulationResponse(
            input_source=input_source,
            saved_to_db=saved,
            ops_input=ops_payload,
            ops_output=output,
        )

    return app


async def _input_for_card(engine, card_id: str) -> OpsAgentInput:
    try:
        payload = await fetch_ops_input(engine, card_id)
    except (SQLAlchemyError, OSError):
        payload = None
    if payload is not None:
        return payload
    example = load_example_input()
    if card_id == example.priority_context.card.card_id:
        return example
    raise HTTPException(status_code=404, detail="card_id를 찾을 수 없습니다.")


async def _save_if_possible(
    engine,
    ops_input: OpsAgentLlmInput,
    output: OpsAgentOutput,
) -> bool:
    card_id = ops_input.handoff_context.audit_context.card_id
    try:
        await save_ops_note(engine, card_id, ops_input, output)
    except (SQLAlchemyError, OSError):
        return False
    return True


def _source_for_card(ops_input: OpsAgentInput, card_id: str) -> str:
    if card_id == ops_input.priority_context.card.card_id:
        return "db_or_example"
    return "example"


app = create_app()
