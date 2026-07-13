from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from heatgrid_ops.agent.errors import (
    AgentDependencyError,
    AgentInputContractError,
    AgentInputNotFoundError,
)


def install_agent_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AgentInputNotFoundError, _agent_error_response)
    app.add_exception_handler(AgentInputContractError, _agent_error_response)
    app.add_exception_handler(AgentDependencyError, _agent_error_response)


async def _agent_error_response(
    _: Request,
    error: Exception,
) -> JSONResponse:
    match error:
        case AgentInputNotFoundError():
            return JSONResponse(status_code=404, content={"detail": str(error)})
        case AgentInputContractError():
            return JSONResponse(status_code=422, content={"detail": str(error)})
        case AgentDependencyError():
            return JSONResponse(status_code=503, content={"detail": str(error)})
        case _:
            raise error
