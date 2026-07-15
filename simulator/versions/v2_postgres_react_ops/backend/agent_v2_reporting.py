from __future__ import annotations

from typing import cast

from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.models import JsonObject, OpsAgentOutput
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_ops.agent.v2_models import StageControlEnvelope, StageSnapshotEnvelope
from heatgrid_ops.agent.v2_stage_contracts import StageAdapter
from heatgrid_ops.agent.v2_state import AgentV2State


def _rag_interpretation() -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        current = dict(state.rag)
        current.update(
            {
                "interpretation": {"status": "unavailable"},
                "execution_status": "unavailable",
                "quality_status": "unavailable",
                "score": None,
            }
        )
        updated = state.model_copy(update={"rag": current})
        return StageSnapshotEnvelope(
            stage_name="rag_interpretation",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=True),
        )

    return execute


def _fault() -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        value: JsonObject = {
            "execution_status": "passed",
            "quality_status": "passed",
            "score": 100.0,
            "evidence_valid": True,
        }
        updated = state.model_copy(update={"fault": value})
        return StageSnapshotEnvelope(
            stage_name="fault_analysis",
            data=updated.model_dump(mode="json"),
        )

    return execute


def _escalation() -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        value: JsonObject = {
            "execution_status": "unavailable",
            "quality_status": "unavailable",
            "score": None,
            "triggered": False,
        }
        updated = state.model_copy(update={"escalation": value})
        return StageSnapshotEnvelope(
            stage_name="higher_model_reassessment",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=True),
        )

    return execute


def _disposition() -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        force_review = any(
            value.get("quality_status") == "unavailable"
            for value in (state.ml, state.weather, state.rag, state.escalation)
            if isinstance(value, dict)
        )
        routing = state.routing.model_copy(
            update={
                "force_review": force_review,
                "disposition": "urgent_review" if force_review else "normal_observation",
            }
        )
        updated = state.model_copy(update={"routing": routing})
        return StageSnapshotEnvelope(
            stage_name="parent_disposition",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=force_review),
        )

    return execute


def _report(runtime: AgentRuntime) -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        evidence = {"rag": state.rag, "weather": state.weather, "fault": state.fault}
        try:
            output = await runtime.generate_llm_output(
                state.request.source_input,
                cast(JsonObject, evidence),
                state.request.card_id,
            )
        except AgentDependencyError:
            output = OpsAgentOutput(
                summary="Report draft unavailable; human review is required.",
                action_plan="Review the persisted stage evidence.",
                caution="The report model was unavailable.",
            )
        value: JsonObject = {
            "execution_status": "passed",
            "quality_status": "passed",
            "score": 100.0,
            "summary": output.summary,
            "action_plan": output.action_plan,
            "caution": output.caution,
        }
        updated = state.model_copy(update={"report": value})
        return StageSnapshotEnvelope(
            stage_name="report_draft",
            data=updated.model_dump(mode="json"),
        )

    return execute


def _fidelity() -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        current = dict(state.report)
        current.update(
            {
                "execution_status": "unavailable",
                "quality_status": "unavailable",
                "score": None,
                "judge": "unavailable",
            }
        )
        updated = state.model_copy(update={"report": current})
        return StageSnapshotEnvelope(
            stage_name="report_fidelity",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=True),
        )

    return execute
