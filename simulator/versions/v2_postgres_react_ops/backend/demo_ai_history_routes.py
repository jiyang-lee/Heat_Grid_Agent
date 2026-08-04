from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


def make_demo_ai_history_router(engine: AsyncEngine, *, enabled: bool) -> APIRouter:
    router = APIRouter(prefix="/api/demo/ai-history", tags=["demo"])

    @router.post("/reset")
    async def reset_ai_history() -> dict[str, object]:
        if not enabled:
            raise HTTPException(status_code=404, detail="demo reset is disabled")
        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_catalog.pg_advisory_xact_lock(82420260718)")
            )
            await connection.execute(
                text("LOCK TABLE public.agent_runs IN ACCESS EXCLUSIVE MODE")
            )
            active_runs = await connection.execute(
                text(
                    "SELECT count(*) FROM public.agent_runs "
                    "WHERE status IN ('queued', 'running')"
                )
            )
            if int(active_runs.scalar_one()) > 0:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "AI 분석이 진행 중입니다. 분석이 완료된 뒤 "
                        "누적 기록을 초기화해 주세요."
                    ),
                )
            runs = await connection.execute(
                text("SELECT count(*) FROM public.agent_runs")
            )
            chats = await connection.execute(
                text("SELECT count(*) FROM public.review_chat_messages")
            )
            artifacts = await connection.execute(
                text("SELECT count(*) FROM public.agent_run_artifacts")
            )
            await connection.execute(
                text("SELECT heatgrid_admin.reset_demo_ai_history()")
            )
        return {
            "reset_at": datetime.now(UTC).isoformat(),
            "deleted_runs": int(runs.scalar_one()),
            "deleted_chat_messages": int(chats.scalar_one()),
            "deleted_artifacts": int(artifacts.scalar_one()),
            "file_warnings": [],
        }

    return router
