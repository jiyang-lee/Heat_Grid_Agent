from __future__ import annotations

from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.contracts import ReportDraftSnapshotBundle
from heatgrid_ops.agent.lineage import canonical_json_hash
from heatgrid_ops.agent.models import JsonObject, OpsAgentOutput
from heatgrid_ops.agent.services import AgentRuntime
from heatgrid_ops.agent.v2_models import StageControlEnvelope, StageSnapshotEnvelope
from heatgrid_ops.agent.v2_stage_contracts import StageAdapter
from heatgrid_ops.agent.v2_state import AgentV2State
from heatgrid_ops.agent.usage import usage_with_totals


def _rag_interpretation() -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        references = state.rag_retrieval.get("references")
        has_references = isinstance(references, dict) and bool(references)
        value: JsonObject = {
            "execution_status": "passed" if has_references else "skipped",
            "quality_status": "partial" if has_references else "skipped",
            "score": 50.0 if has_references else None,
            "claims": [],
            "conflicts": [],
            "unsupported_topics": ["fault_cause"] if has_references else [],
        }
        updated = state.model_copy(update={"rag_interpretation": value})
        return StageSnapshotEnvelope(
            stage_name="rag_interpretation",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=False),
        )

    return execute


def _fault() -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        value: JsonObject = {
            "execution_status": "unavailable",
            "quality_status": "insufficient",
            "score": None,
            "fault_confirmed": False,
            "unknown_reason": "fault_classifier_unavailable",
        }
        updated = state.model_copy(update={"fault_analysis": value})
        return StageSnapshotEnvelope(
            stage_name="fault_analysis",
            data=updated.model_dump(mode="json"),
        )

    return execute


def _escalation(runtime: AgentRuntime) -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        triggered = state.ml_validation.get("quality_status") in {
            "insufficient",
            "unavailable",
        }
        if triggered:
            bundle_data: JsonObject = {
                "ml_validation": state.ml_validation,
                "weather_context": state.weather_context,
                "rag_retrieval": state.rag_retrieval,
                "rag_interpretation": state.rag_interpretation,
                "fault_analysis": state.fault_analysis,
            }
            bundle = ReportDraftSnapshotBundle(
                run_id=state.request.run_id,
                root_run_id=state.request.run_id,
                target_stage="higher_model_reassessment",
                source_input_hash=state.request.input_hash,
                bundle_hash=canonical_json_hash(bundle_data),
                stages=bundle_data,
            )
            try:
                output = await runtime.reassess_with_high_model(
                    state.request.source_input,
                    bundle_data,
                    state.request.card_id,
                    run_id=state.request.run_id,
                    snapshot_bundle=bundle,
                )
            except AgentDependencyError:
                value: JsonObject = {
                    "execution_status": "unavailable",
                    "quality_status": "insufficient",
                    "score": None,
                    "triggered": True,
                }
            else:
                value = {
                    "execution_status": "passed",
                    "quality_status": "passed",
                    "score": 100.0,
                    "triggered": True,
                    "summary": output.summary,
                    "action_plan": output.action_plan,
                    "caution": output.caution,
                }
        else:
            value = {
                "execution_status": "skipped",
                "quality_status": "skipped",
                "score": None,
                "triggered": False,
            }
        updated = state.model_copy(update={"higher_model_reassessment": value})
        return StageSnapshotEnvelope(
            stage_name="higher_model_reassessment",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=value["quality_status"] != "passed"),
        )

    return execute


def _disposition() -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        force_review = state.ml_validation.get("quality_status") in {
            "insufficient",
            "unavailable",
        } or state.fault_analysis.get("quality_status") in {"insufficient", "unavailable"}
        routing = state.parent_disposition.model_copy(
            update={
                "force_review": force_review,
                "disposition": "inspection_recommended" if force_review else "normal_observation",
            }
        )
        updated = state.model_copy(update={"parent_disposition": routing})
        return StageSnapshotEnvelope(
            stage_name="parent_disposition",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=force_review),
        )

    return execute


def _report(runtime: AgentRuntime) -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        evidence: JsonObject = {
            "ml_validation": state.ml_validation,
            "weather_context": state.weather_context,
            "rag_retrieval": state.rag_retrieval,
            "rag_interpretation": state.rag_interpretation,
            "fault_analysis": state.fault_analysis,
            "higher_model_reassessment": state.higher_model_reassessment,
            "parent_disposition": state.parent_disposition.model_dump(mode="json"),
        }
        usage = runtime.token_usage_for(
            state.request.source_input,
            evidence,
            state.request.card_id,
        )
        bundle_data: JsonObject = {
            "ml_validation": state.ml_validation,
            "weather_context": state.weather_context,
            "rag_retrieval": state.rag_retrieval,
            "rag_interpretation": state.rag_interpretation,
            "fault_analysis": state.fault_analysis,
            "higher_model_reassessment": state.higher_model_reassessment,
            "parent_disposition": state.parent_disposition.model_dump(mode="json"),
        }
        bundle_hash = canonical_json_hash(bundle_data)
        bundle = ReportDraftSnapshotBundle(
            run_id=state.request.run_id,
            root_run_id=state.request.run_id,
            target_stage=state.request.target_stage,
            source_input_hash=state.request.input_hash,
            bundle_hash=bundle_hash,
            stages=bundle_data,
        )
        try:
            output = await runtime.generate_llm_output(
                state.request.source_input,
                evidence,
                state.request.card_id,
                usage=usage,
                run_id=state.request.run_id,
                stage_name="report_draft",
                stage_attempt=state.attempts.get("report_draft", 1),
                execution_profile="report_snapshot_only",
                snapshot_bundle=bundle,
            )
        except AgentDependencyError:
            output = OpsAgentOutput(
                summary="Report draft unavailable; human review is required.",
                action_plan="Review the persisted stage evidence.",
                caution="The report model was unavailable.",
            )
        usage_with_totals(usage, runtime.config)
        value: JsonObject = {
            "execution_status": "passed",
            "quality_status": "passed",
            "score": 100.0,
            "summary": output.summary,
            "action_plan": output.action_plan,
            "caution": output.caution,
            "token_usage": usage.model_dump(mode="json"),
            "execution_profile": "report_snapshot_only",
            "snapshot_bundle_hash": bundle_hash,
            "tool_call_count": 0,
            "model_call_count": usage.model_calls,
        }
        updated = state.model_copy(update={"report_draft": value})
        return StageSnapshotEnvelope(
            stage_name="report_draft",
            data=updated.model_dump(mode="json"),
        )

    return execute


def _fidelity() -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        has_report = all(
            isinstance(state.report_draft.get(field), str) and state.report_draft[field]
            for field in ("summary", "action_plan", "caution")
        )
        value: JsonObject = {
            "execution_status": "passed" if has_report else "failed",
            "quality_status": "passed" if has_report else "insufficient",
            "score": 100.0 if has_report else None,
            "judge": "deterministic",
        }
        updated = state.model_copy(update={"report_fidelity": value})
        return StageSnapshotEnvelope(
            stage_name="report_fidelity",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=not has_report),
        )

    return execute
