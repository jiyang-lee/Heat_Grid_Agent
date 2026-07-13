from __future__ import annotations

from typing import Protocol

from heatgrid_ops.agent.contracts import SimulateCard
from heatgrid_ops.agent.ports import (
    ArtifactPort,
    AgentInputPort,
    ReviewPort,
    RunAuditPort,
    RunLifecyclePort,
)
from heatgrid_ops.agent.services import AgentRuntime


class AgentNodeContext(Protocol):
    @property
    def runtime(self) -> AgentRuntime: ...

    @property
    def inputs(self) -> AgentInputPort: ...

    @property
    def lifecycle(self) -> RunLifecyclePort: ...

    @property
    def audit(self) -> RunAuditPort: ...

    @property
    def reviews(self) -> ReviewPort: ...

    @property
    def artifacts(self) -> ArtifactPort: ...

    @property
    def legacy_simulate_card(self) -> SimulateCard | None: ...
