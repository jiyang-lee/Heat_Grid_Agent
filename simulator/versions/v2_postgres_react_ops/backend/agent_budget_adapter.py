from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine

from agent_budget_repository import (
    finish_diagnostic_budget,
    reserve_diagnostic_budget,
)
from heatgrid_ops.agent.diagnostics import DiagnosticBudgetReservation


@dataclass(frozen=True, slots=True)
class PostgresAgentBudgetAdapter:
    engine: AsyncEngine

    async def reserve_diagnostic(
        self,
        run_id: str,
        token_limit: int,
    ) -> DiagnosticBudgetReservation:
        return await reserve_diagnostic_budget(
            self.engine,
            run_id=run_id,
            token_limit=token_limit,
        )

    async def finish_diagnostic(
        self,
        reservation_id: str,
        *,
        tokens_used: int,
        model_called: bool,
    ) -> None:
        await finish_diagnostic_budget(
            self.engine,
            reservation_id=reservation_id,
            tokens_used=tokens_used,
            model_called=model_called,
        )
