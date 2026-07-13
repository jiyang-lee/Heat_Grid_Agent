from __future__ import annotations

from types import SimpleNamespace

import pytest

from heatgrid_ops.agent.contracts import AgentInputSnapshot, AgentRunRequest
from heatgrid_ops.agent.errors import (
    AgentInputContractError,
    AgentInputNotFoundError,
)
from heatgrid_ops.agent.nodes import load_ops_input
from heatgrid_ops.agent.ports import (
    ArtifactPort,
    ChatModelPort,
    ExternalDataPort,
    ModelVerificationPort,
    RagEvidencePort,
    ReportWriterPort,
    ReviewPort,
    RunAuditPort,
    RunLifecyclePort,
)
from heatgrid_ops.agent.run_models import ExternalDataRequest


class FakeAgentInputPort:
    def __init__(self, snapshot: AgentInputSnapshot | None) -> None:
        self.snapshot = snapshot
        self.requests: list[AgentRunRequest] = []

    async def load(self, request: AgentRunRequest) -> AgentInputSnapshot | None:
        self.requests.append(request)
        return self.snapshot


def test_core_exposes_narrow_runtime_ports() -> None:
    assert RunLifecyclePort
    assert RunAuditPort
    assert ExternalDataPort
    assert RagEvidencePort
    assert ChatModelPort
    assert ModelVerificationPort
    assert ReportWriterPort
    assert ReviewPort
    assert ArtifactPort


def test_external_data_request_rejects_generic_network_inputs() -> None:
    with pytest.raises(Exception):
        ExternalDataRequest.model_validate(
            {
                "substation_id": 31,
                "window_start": "2020-01-11T00:00:00+09:00",
                "window_end": "2020-01-11T06:00:00+09:00",
                "url": "https://example.com",
                "query": "search the web",
                "domain": "example.com",
            }
        )


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
