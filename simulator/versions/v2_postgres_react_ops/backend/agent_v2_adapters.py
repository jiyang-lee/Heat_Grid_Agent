from __future__ import annotations

from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.quality import ml_quality_result
from heatgrid_ops.agent.run_models import (
    ExternalDataRequest,
    ModelVerificationRequest,
    RagEvidenceRequest,
)
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_ops.agent.v2_models import (
    StageControlEnvelope,
    StageName,
    StageSnapshotEnvelope,
)
from heatgrid_ops.agent.v2_stage_contracts import StageAdapter
from heatgrid_ops.agent.v2_state import AgentV2State
from agent_v2_reporting import (
    _disposition,
    _escalation,
    _fault,
    _fidelity,
    _rag_interpretation,
    _report,
)


def make_v2_adapters(
    runtime: AgentRuntime,
    *,
    rag_quality_enabled: bool,
) -> dict[StageName, StageAdapter]:
    return {
        "ml_validation": _ml(runtime),
        "weather_context": _weather(runtime),
        "rag_retrieval": _rag_retrieval(runtime, rag_quality_enabled),
        "rag_interpretation": _rag_interpretation(),
        "fault_analysis": _fault(),
        "higher_model_reassessment": _escalation(runtime),
        "parent_disposition": _disposition(),
        "report_draft": _report(runtime),
        "report_fidelity": _fidelity(),
    }


def _ml(runtime: AgentRuntime) -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        snapshot = await runtime.verify_models(
            ModelVerificationRequest(
                card_id=state.request.card_id,
                source_input=state.request.source_input,
                attempt=state.attempts.get("ml_validation", 1),
            )
        )
        result = snapshot.result
        quality = ml_quality_result(status=result.status, agreement=result.agreement)
        value = {
            **result.model_dump(mode="json"),
            "artifact_uri": snapshot.artifact_uri,
            "execution_status": quality.execution_status,
            "quality_status": quality.quality_status,
            "score": quality.score,
        }
        updated = state.model_copy(update={"ml_validation": value})
        return StageSnapshotEnvelope(
            stage_name="ml_validation",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=quality.quality_status != "passed"),
        )

    return execute


def _weather(runtime: AgentRuntime) -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        request = _external_request(state.request.source_input)
        if request is None:
            value: JsonObject = {
                "execution_status": "skipped",
                "quality_status": "skipped",
                "score": None,
                "weather": {"status": "unavailable"},
            }
        else:
            snapshot = await runtime.external_data.snapshot(request)
            value = {
                "execution_status": "passed",
                "quality_status": "passed"
                if snapshot.status == "available"
                else "unavailable",
                "score": 100.0 if snapshot.status == "available" else None,
                "weather": snapshot.weather,
                "site": snapshot.site,
            }
        updated = state.model_copy(update={"weather_context": value})
        return StageSnapshotEnvelope(
            stage_name="weather_context",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=value["quality_status"] == "unavailable"),
        )

    return execute


def _rag_retrieval(
    runtime: AgentRuntime,
    quality_enabled: bool,
) -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        snapshot = await runtime.rag.search(
            RagEvidenceRequest(
                card_id=state.request.card_id,
                source_input=state.request.source_input,
                top_k=runtime.config.rag_top_k,
            )
        )
        quality_status = "skipped" if not quality_enabled else "partial"
        score = None if not quality_enabled else 0.0
        value: JsonObject = {
            "execution_status": "passed",
            "quality_status": quality_status,
            "score": score,
            "retrieval": snapshot.retrieval,
            "references": snapshot.references,
            "status": snapshot.status,
        }
        updated = state.model_copy(update={"rag_retrieval": value})
        return StageSnapshotEnvelope(
            stage_name="rag_retrieval",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=False),
        )

    return execute


def _external_request(source_input: JsonObject) -> ExternalDataRequest | None:
    raw_context = source_input.get("raw_context")
    if not isinstance(raw_context, dict):
        return None
    window = raw_context.get("window")
    if not isinstance(window, dict):
        return None
    uid = window.get("substation_uid")
    substation_id = window.get("substation_id")
    start = window.get("window_start")
    end = window.get("window_end")
    if not isinstance(uid, str) or not isinstance(substation_id, int):
        return None
    if not isinstance(start, str) or not isinstance(end, str):
        return None
    return ExternalDataRequest(
        substation_uid=uid,
        substation_id=substation_id,
        window_start=start,
        window_end=end,
    )
