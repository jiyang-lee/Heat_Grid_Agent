from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import orjson
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from heatgrid_ops.agent.lineage import canonical_json_hash
from heatgrid_ops.agent.models import JsonObject


InputSnapshotOrigin = Literal["native_v2", "legacy_reconstructed_v008", "legacy_v1"]
InputSnapshotStatus = Literal["available", "unavailable"]
INPUT_SCHEMA_VERSION = "agent_input.v2"


@dataclass(frozen=True, slots=True)
class AgentInputLineage:
    run_id: str
    source_input: JsonObject | None
    input_schema_version: str | None
    input_hash: str | None
    origin: InputSnapshotOrigin
    status: InputSnapshotStatus


async def get_agent_input_lineage(
    engine: AsyncEngine,
    run_id: str,
) -> AgentInputLineage | None:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT run_id, CAST(source_input_snapshot AS text) AS source_input_snapshot, "
                "input_schema_version, input_hash, input_snapshot_origin, "
                "input_snapshot_status FROM agent_runs WHERE run_id = :run_id"
            ),
            {"run_id": run_id},
        )
    row = result.mappings().one_or_none()
    if row is None:
        return None
    raw_snapshot = row["source_input_snapshot"]
    return AgentInputLineage(
        run_id=str(row["run_id"]),
        source_input=None if raw_snapshot is None else orjson.loads(raw_snapshot),
        input_schema_version=row["input_schema_version"],
        input_hash=row["input_hash"],
        origin=row["input_snapshot_origin"],
        status=row["input_snapshot_status"],
    )


async def persist_native_agent_input(
    engine: AsyncEngine,
    *,
    run_id: str,
    source_input: JsonObject,
) -> AgentInputLineage:
    input_hash = canonical_json_hash(source_input)
    payload = orjson.dumps(source_input, option=orjson.OPT_SORT_KEYS).decode("utf-8")
    async with engine.begin() as connection:
        result = await connection.execute(
            text(
                "UPDATE agent_runs SET source_input_snapshot = CAST(:snapshot AS jsonb), "
                "input_schema_version = :schema_version, input_hash = :input_hash, "
                "input_snapshot_origin = 'native_v2', input_snapshot_status = 'available', "
                "reconstructed_at = NULL WHERE run_id = :run_id "
                "AND input_snapshot_origin = 'native_v2' "
                "AND input_snapshot_status = 'unavailable' RETURNING run_id"
            ),
            {
                "run_id": run_id,
                "snapshot": payload,
                "schema_version": INPUT_SCHEMA_VERSION,
                "input_hash": input_hash,
            },
        )
        if result.scalar_one_or_none() is None:
            existing = await connection.execute(
                text(
                    "SELECT input_hash, input_snapshot_status FROM agent_runs "
                    "WHERE run_id = :run_id FOR UPDATE"
                ),
                {"run_id": run_id},
            )
            row = existing.mappings().one_or_none()
            if row is None:
                raise ValueError("run_id was not found")
            if row["input_snapshot_status"] != "available" or row["input_hash"] != input_hash:
                raise ValueError("agent input snapshot is immutable")
    lineage = await get_agent_input_lineage(engine, run_id)
    if lineage is None:
        raise ValueError("run_id was not found")
    return lineage
