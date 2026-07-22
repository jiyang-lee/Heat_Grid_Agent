from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Final

from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
import pytest

from heatgrid_ops.agent.errors import (
    AgentCoreError,
    AgentDependencyError,
    AgentInputContractError,
    AgentInputNotFoundError,
)


ROOT: Final = Path(__file__).resolve().parents[1]
BACKEND: Final = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"


def _install_agent_error_handlers(app: FastAPI) -> None:
    spec = spec_from_file_location(
        "test_agent_error_mapping",
        BACKEND / "agent_error_mapping.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("agent error mapper could not be loaded")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    install = vars(module).get("install_agent_error_handlers")
    if not callable(install):
        raise RuntimeError("agent error mapper has no installer")
    install(app)


def test_core_errors_do_not_inherit_fastapi_http_exception() -> None:
    error = AgentInputNotFoundError(entity="card_id", identifier="card-404")

    assert isinstance(error, AgentCoreError)
    assert not isinstance(error, HTTPException)


@pytest.mark.anyio
async def test_http_boundary_maps_typed_core_errors() -> None:
    app = FastAPI()
    _install_agent_error_handlers(app)

    @app.get("/not-found")
    async def not_found() -> None:
        raise AgentInputNotFoundError(entity="card_id", identifier="card-404")

    @app.get("/contract")
    async def contract() -> None:
        raise AgentInputContractError(detail="priority_context 형식 오류")

    @app.get("/dependency")
    async def dependency() -> None:
        raise AgentDependencyError(service="llm", detail="OPENAI_API_KEY가 필요합니다.")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        not_found_response = await client.get("/not-found")
        contract_response = await client.get("/contract")
        dependency_response = await client.get("/dependency")

    assert not_found_response.status_code == 404
    assert not_found_response.json() == {"detail": "card_id를 찾을 수 없습니다."}
    assert contract_response.status_code == 422
    assert contract_response.json() == {"detail": "priority_context 형식 오류"}
    assert dependency_response.status_code == 503
    assert dependency_response.json() == {"detail": "OPENAI_API_KEY가 필요합니다."}
