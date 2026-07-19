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
            await connection.execute(text("SELECT pg_advisory_xact_lock(82420260718)"))
            runs = await connection.execute(text("SELECT count(*) FROM agent_runs"))
            chats = await connection.execute(text("SELECT count(*) FROM review_chat_messages"))
            artifacts = await connection.execute(text("SELECT count(*) FROM agent_run_artifacts"))
            await connection.execute(text("TRUNCATE TABLE agent_runs CASCADE"))
        return {
            "reset_at": datetime.now(UTC).isoformat(),
            "deleted_runs": int(runs.scalar_one()),
            "deleted_chat_messages": int(chats.scalar_one()),
            "deleted_artifacts": int(artifacts.scalar_one()),
            "file_warnings": [],
        }

    return router
