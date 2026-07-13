from __future__ import annotations

from typing import Protocol

from heatgrid_ops.agent.contracts import SimulateCard
from heatgrid_ops.agent.ports import (
    AgentArtifactPort,
    AgentInputPort,
    AgentModelDataPort,
    AgentReviewPort,
    AgentRunAuditPort,
    AgentRunLifecyclePort,
)
from heatgrid_ops.agent.services import AgentRuntime


class AgentNodeContext(Protocol):
    @property
    def runtime(self) -> AgentRuntime: ...

    @property
    def inputs(self) -> AgentInputPort: ...

    @property
    def lifecycle(self) -> AgentRunLifecyclePort: ...

    @property
    def audit(self) -> AgentRunAuditPort: ...

    @property
    def model_data(self) -> AgentModelDataPort: ...

    @property
    def reviews(self) -> AgentReviewPort: ...

    @property
    def artifacts(self) -> AgentArtifactPort: ...

    @property
    def legacy_simulate_card(self) -> SimulateCard | None: ...
