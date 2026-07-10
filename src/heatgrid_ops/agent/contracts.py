from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from schemas import SimulationResponse

type SimulateCard = Callable[[str], Awaitable[SimulationResponse]]


@dataclass(frozen=True, slots=True)
class AgentRunRequest:
    run_id: str
    alert_id: str
    card_id: str
