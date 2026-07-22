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
        if request.mode == "stored_snapshot":
            return ModelVerificationSnapshot(result=_stored_snapshot_result(request.source_input, request.attempt))
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
        result = result.model_copy(update={"verification_source": "active_revalidation"})
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


def _stored_snapshot_result(source_input: dict[str, JsonValue], attempt: int):
    context = source_input.get("evaluation_context")
    evaluation = context.get("evaluation") if isinstance(context, dict) else None
    result = context.get("result") if isinstance(context, dict) else None
    if not isinstance(result, dict):
        from heatgrid_ops.agent.models import ModelVerificationResult
        return ModelVerificationResult(status="partial", attempt=attempt, reasons=["stored prediction snapshot is unavailable"], verification_source="stored_snapshot")
    from heatgrid_ops.agent.models import ModelVerificationResult
    risk = result.get("risk_score")
    priority = result.get("priority_score")
    leadtime = result.get("leadtime_bucket")
    sufficient = isinstance(risk, (int, float)) and isinstance(priority, (int, float)) and isinstance(leadtime, str)
    return ModelVerificationResult(
        status="verified" if sufficient else "partial",
        attempt=attempt,
        risk_score=float(risk) if isinstance(risk, (int, float)) else None,
        stored_risk_score=float(risk) if isinstance(risk, (int, float)) else None,
        priority_score=float(priority) if isinstance(priority, (int, float)) else None,
        stored_priority_score=float(priority) if isinstance(priority, (int, float)) else None,
        leadtime_bucket=leadtime if isinstance(leadtime, str) else None,
        stored_leadtime_bucket=leadtime if isinstance(leadtime, str) else None,
        agreement=True if sufficient else None,
        evaluation_run_id=evaluation.get("evaluation_run_id") if isinstance(evaluation, dict) else None,
        manufacturer_id=result.get("manufacturer_id") if isinstance(result.get("manufacturer_id"), str) else None,
        substation_id=result.get("substation_id") if isinstance(result.get("substation_id"), int) else None,
        reasons=["stored priority-evaluation snapshot reused"],
        verification_source="stored_snapshot",
    )
