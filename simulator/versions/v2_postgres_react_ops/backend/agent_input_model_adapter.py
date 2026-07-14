from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from pathlib import Path

from anyio.to_thread import run_sync
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_input_snapshot_repository import get_agent_input_lineage
from alert_repository import get_alert
from heatgrid_ops.agent.contracts import AgentInputSnapshot, AgentRunRequest
from heatgrid_ops.agent.models import JsonObject, JsonValue
from heatgrid_ops.agent.run_models import ModelInferenceSnapshot
from heatgrid_ops.priority.evaluation import get_priority_evaluation_result
from heatgrid_ops.priority.inference import (
    PriorityInferenceError,
    PriorityInferenceRuntime,
)
from model_feature_repository import fetch_model_feature_snapshot
from repository import fetch_ops_input
from retrain_repository import get_active_model_deployment


ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True, slots=True)
class PostgresAgentInputModelAdapter:
    engine: AsyncEngine

    async def load(self, request: AgentRunRequest) -> AgentInputSnapshot | None:
        lineage = await get_agent_input_lineage(self.engine, request.run_id)
        if lineage is not None and lineage.status == "available":
            if lineage.source_input is None:
                raise ValueError("available agent input snapshot is missing")
            return AgentInputSnapshot(source_input=lineage.source_input)
        source_input = await fetch_ops_input(self.engine, request.card_id)
        if source_input is None:
            return None
        alert = await get_alert(self.engine, request.alert_id)
        evaluation_context = await _evaluation_context(self.engine, alert)
        if evaluation_context is not None:
            source_input["evaluation_context"] = evaluation_context
            sections = source_input.get("sections")
            if isinstance(sections, dict):
                sections["evaluation"] = evaluation_context
        return AgentInputSnapshot(source_input=source_input)

    async def feature_values(self, card_id: str) -> dict[str, float]:
        return await fetch_model_feature_snapshot(self.engine, card_id)

    async def active_artifact_uri(self) -> str | None:
        deployment = await get_active_model_deployment(self.engine)
        return None if deployment is None else deployment.artifact_uri

    async def infer(
        self,
        feature_values: dict[str, float],
        source_input: JsonObject,
        active_artifact_uri: str | None,
    ) -> ModelInferenceSnapshot:
        return await run_sync(
            partial(
                _infer_model,
                feature_values,
                source_input,
                active_artifact_uri,
            )
        )


def _infer_model(
    feature_values: dict[str, float],
    source_input: JsonObject,
    active_artifact_uri: str | None,
) -> ModelInferenceSnapshot:
    try:
        runtime = PriorityInferenceRuntime(
            model_root=_model_root(active_artifact_uri),
            deployment_version=_deployment_version(active_artifact_uri),
        )
        inference = runtime.infer_batch(
            [
                {
                    **_source_identity(source_input),
                    "feature_values": feature_values,
                }
            ]
        )[0]
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        PriorityInferenceError,
    ) as exc:
        return ModelInferenceSnapshot(error=str(exc))
    return ModelInferenceSnapshot(
        usable=bool(inference.get("usable")),
        payload=inference,
    )


async def _evaluation_context(
    engine: AsyncEngine,
    alert: dict[str, JsonValue] | None,
) -> JsonObject | None:
    if alert is None:
        return None
    evaluation_run_id = _text(alert.get("evaluation_run_id"))
    substation_uid = _text(alert.get("substation_uid"))
    substation_id = _integer(alert.get("substation_id"))
    if evaluation_run_id is None or (substation_uid is None and substation_id is None):
        return None
    try:
        return await get_priority_evaluation_result(
            engine,
            evaluation_run_id,
            substation_id,
            manufacturer_id=_text(alert.get("manufacturer_id")),
            substation_uid=substation_uid,
        )
    except (TypeError, ValueError):
        return None


def _source_identity(source_input: JsonObject) -> JsonObject:
    evaluation_context = _mapping(source_input.get("evaluation_context"))
    evaluation_result = _mapping(evaluation_context.get("result"))
    raw_context = _mapping(source_input.get("raw_context"))
    window = _mapping(raw_context.get("window"))
    substation = _mapping(raw_context.get("substation"))
    return {
        "substation_uid": evaluation_result.get("substation_uid")
        or window.get("substation_uid")
        or substation.get("substation_uid"),
        "manufacturer_id": evaluation_result.get("manufacturer_id")
        or window.get("manufacturer_id")
        or window.get("manufacturer"),
        "substation_id": evaluation_result.get("substation_id")
        or window.get("substation_id")
        or substation.get("substation_id"),
        "configuration_type": substation.get("configuration_type")
        or window.get("configuration_type"),
    }


def _model_root(active_artifact_uri: str | None) -> Path:
    if active_artifact_uri:
        candidate = Path(active_artifact_uri)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        nested = candidate / "models"
        return nested if nested.exists() else candidate
    return ROOT / "models"


def _deployment_version(active_artifact_uri: str | None) -> str:
    if active_artifact_uri is None:
        return "active-local-model"
    return f"active-deployment-{Path(active_artifact_uri).name}"


def _mapping(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _text(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _integer(value: JsonValue | None) -> int | None:
    match value:
        case bool() | None:
            return None
        case int():
            return value
        case str():
            try:
                return int(value)
            except ValueError:
                return None
        case _:
            return None
