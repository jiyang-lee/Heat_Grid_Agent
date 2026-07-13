from __future__ import annotations

from types import SimpleNamespace

import pytest

from heatgrid_ops.agent.contracts import AgentInputSnapshot, AgentRunRequest
from heatgrid_ops.agent.errors import (
    AgentInputContractError,
    AgentInputNotFoundError,
)
from heatgrid_ops.agent.nodes import load_ops_input


class FakeAgentInputPort:
    def __init__(self, snapshot: AgentInputSnapshot | None) -> None:
        self.snapshot = snapshot
        self.requests: list[AgentRunRequest] = []

    async def load(self, request: AgentRunRequest) -> AgentInputSnapshot | None:
        self.requests.append(request)
        return self.snapshot


@pytest.mark.anyio
async def test_load_ops_input_uses_typed_input_port() -> None:
    source_input = {
        "card_id": "card-1",
        "sections": {},
        "priority_context": {
            "card": {"card_id": "card-1"},
            "priority": {"priority_level": "high"},
        },
        "raw_context": {},
    }
    input_port = FakeAgentInputPort(AgentInputSnapshot(source_input=source_input))
    state = {"run_id": "run-1", "alert_id": "alert-1", "card_id": "card-1"}

    result = await load_ops_input(SimpleNamespace(inputs=input_port), state)

    assert result == {"source_input": source_input}
    assert input_port.requests == [
        AgentRunRequest(run_id="run-1", alert_id="alert-1", card_id="card-1")
    ]


@pytest.mark.anyio
async def test_load_ops_input_raises_typed_not_found_error() -> None:
    input_port = FakeAgentInputPort(None)
    state = {"run_id": "run-1", "alert_id": "alert-1", "card_id": "card-404"}

    with pytest.raises(AgentInputNotFoundError) as captured:
        await load_ops_input(SimpleNamespace(inputs=input_port), state)

    assert captured.value.entity == "card_id"
    assert captured.value.identifier == "card-404"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("source_input", "detail"),
    [
        (
            {},
            "agent input missing required keys: card_id, sections, priority_context, raw_context",
        ),
        (
            {
                "card_id": "card-other",
                "sections": {},
                "priority_context": {},
                "raw_context": {},
            },
            "agent input card_id does not match requested card_id",
        ),
    ],
)
async def test_load_ops_input_rejects_invalid_source_contract(
    source_input: dict[str, object],
    detail: str,
) -> None:
    input_port = FakeAgentInputPort(AgentInputSnapshot(source_input=source_input))
    state = {"run_id": "run-1", "alert_id": "alert-1", "card_id": "card-1"}

    with pytest.raises(AgentInputContractError) as captured:
        await load_ops_input(SimpleNamespace(inputs=input_port), state)

    assert str(captured.value) == detail
