from __future__ import annotations

from dataclasses import dataclass

from agent_input_model_adapter import PostgresAgentInputModelAdapter
from heatgrid_ops.agent.model_verification import verify_models
from heatgrid_ops.agent.models import JsonValue
from heatgrid_ops.agent.run_models import (
    ModelVerificationRequest,
    ModelVerificationSnapshot,
)


@dataclass(frozen=True, slots=True)
class ActiveModelVerificationAdapter:
    model_data: PostgresAgentInputModelAdapter
    tolerance: float

    async def verify(
        self,
        request: ModelVerificationRequest,
    ) -> ModelVerificationSnapshot:
        features = await self.model_data.feature_values(request.card_id)
        if not features:
            features = _feature_values_from_source(request.source_input)
        artifact_uri = await self.model_data.active_artifact_uri()
        inference = await self.model_data.infer(
            features,
            request.source_input,
            artifact_uri,
        )
        result = verify_models(
            inference,
            features,
            request.source_input,
            tolerance=self.tolerance,
            attempt=request.attempt,
        )
        evaluation_context = request.source_input.get("evaluation_context")
        if isinstance(evaluation_context, dict):
            evaluation = evaluation_context.get("evaluation")
            snapshot_result = evaluation_context.get("result")
            result = result.model_copy(
                update={
                    "evaluation_run_id": evaluation.get("evaluation_run_id")
                    if isinstance(evaluation, dict)
                    else None,
                    "manufacturer_id": snapshot_result.get("manufacturer_id")
                    if isinstance(snapshot_result, dict)
                    else None,
                    "substation_id": snapshot_result.get("substation_id")
                    if isinstance(snapshot_result, dict)
                    else None,
                }
            )
        return ModelVerificationSnapshot(result=result, artifact_uri=artifact_uri)


def _feature_values_from_source(source_input: dict[str, JsonValue]) -> dict[str, float]:
    raw_context = source_input.get("raw_context")
    summaries = raw_context.get("sensor_summaries") if isinstance(raw_context, dict) else None
    if not isinstance(summaries, list):
        return {}
    values: dict[str, float] = {}
    for item in summaries:
        if not isinstance(item, dict):
            continue
        name = item.get("feature_name")
        value = item.get("feature_value")
        if not isinstance(name, str) or not isinstance(value, (int, float, str)):
            continue
        try:
            values[name] = float(value)
        except (TypeError, ValueError):
            continue
    return values
