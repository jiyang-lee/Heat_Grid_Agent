from __future__ import annotations

from heatgrid_ops.agent.answer_quality import (
    AnswerQualityDecision,
    evaluate_against_baseline,
    needs_retrieval_expansion,
    select_answer_variant,
    strict_revision_feedback,
)
from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.contracts import ReportDraftSnapshotBundle
from heatgrid_ops.agent.lineage import canonical_json_hash
from heatgrid_ops.agent.models import JsonObject, OpsAgentOutput, TokenUsage
from heatgrid_ops.agent.rag_quality import evaluate_retrieval_quality, rerank_retrieval
from heatgrid_ops.agent.run_models import AnswerQualityEvaluation, RagEvidenceRequest
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
        bundle = _report_bundle(state, evidence)
        bundle_hash = bundle.bundle_hash
        generation_available = True
        try:
            initial_output = await runtime.generate_llm_output(
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
            generation_available = False
            initial_output = OpsAgentOutput(
                summary="Report draft unavailable; human review is required.",
                action_plan="Review the persisted stage evidence.",
                caution="The report model was unavailable.",
            )

        threshold = runtime.config.answer_quality_threshold
        quality_enabled = (
            runtime.config.answer_quality_enabled
            and state.request.target_stage is None
            and generation_available
        )
        initial_evaluation: AnswerQualityEvaluation | None = None
        initial_decision: AnswerQualityDecision | None = None
        regenerated_output: OpsAgentOutput | None = None
        regenerated_evaluation: AnswerQualityEvaluation | None = None
        regenerated_decision: AnswerQualityDecision | None = None
        selected_output = initial_output
        selected_decision: AnswerQualityDecision | None = None
        selected_variant = "initial"
        selection_reason = "quality_gate_disabled_for_this_run"
        evaluation_error: str | None = None
        selected_bundle_hash = bundle_hash
        regeneration_evidence = evidence
        regeneration_bundle = bundle
        retrieval_expansion: JsonObject = {
            "requested": False,
            "status": "not_needed",
            "candidate_top_k": None,
            "candidate_count": 0,
            "selected_count": 0,
            "selected_chunk_ids": [],
            "original_ranks": [],
            "method": None,
            "error": None,
        }

        if quality_enabled:
            try:
                (
                    initial_evaluation,
                    initial_decision,
                ) = await _evaluate_once(
                    runtime,
                    run_id=state.request.run_id,
                    source_input=state.request.source_input,
                    evidence_context=evidence,
                    answer=initial_output,
                    usage=usage,
                    threshold=threshold,
                )
            except AgentDependencyError as exc:
                evaluation_error = f"{exc.service}_unavailable"
                selection_reason = "initial_quality_evaluation_unavailable"
            else:
                selected_decision = initial_decision
                selection_reason = "initial_answer_met_baseline"
                if not initial_decision.passed:
                    selection_reason = "regeneration_unavailable"
                    if needs_retrieval_expansion(initial_evaluation):
                        retrieval_expansion["requested"] = True
                        retrieval_expansion["status"] = "unavailable"
                        try:
                            (
                                expanded_rag,
                                expansion_metadata,
                            ) = await _expanded_rag_for_revision(runtime, state)
                        except Exception as exc:
                            retrieval_expansion["error"] = (
                                f"{type(exc).__name__}_unavailable"
                            )
                        else:
                            retrieval_expansion = {
                                **retrieval_expansion,
                                **expansion_metadata,
                                "requested": True,
                                "status": "passed",
                                "error": None,
                            }
                            regeneration_evidence = {
                                **evidence,
                                "rag_retrieval": expanded_rag,
                            }
                            regeneration_bundle = _report_bundle(
                                state,
                                regeneration_evidence,
                            )
                    try:
                        regenerated_output = await runtime.generate_llm_output(
                            state.request.source_input,
                            regeneration_evidence,
                            state.request.card_id,
                            revision_feedback=[
                                "Original draft to improve: "
                                + initial_output.model_dump_json(),
                                *strict_revision_feedback(initial_evaluation),
                            ],
                            usage=usage,
                            run_id=state.request.run_id,
                            stage_name="report_draft",
                            stage_attempt=state.attempts.get("report_draft", 1),
                            execution_profile="report_revision_only",
                            snapshot_bundle=regeneration_bundle,
                        )
                        (
                            regenerated_evaluation,
                            regenerated_decision,
                        ) = await _evaluate_once(
                            runtime,
                            run_id=state.request.run_id,
                            source_input=state.request.source_input,
                            evidence_context=regeneration_evidence,
                            answer=regenerated_output,
                            usage=usage,
                            threshold=threshold,
                        )
                    except AgentDependencyError as exc:
                        evaluation_error = f"{exc.service}_unavailable"
                    else:
                        selected_variant, selection_reason = select_answer_variant(
                            initial_decision,
                            regenerated_decision,
                        )
                        if selected_variant == "regenerated":
                            selected_output = regenerated_output
                            selected_decision = regenerated_decision
                            selected_bundle_hash = regeneration_bundle.bundle_hash

        if not generation_available:
            selection_reason = "initial_generation_unavailable"

        usage_with_totals(usage, runtime.config)
        if selected_decision is None:
            quality_status = (
                "unavailable"
                if runtime.config.answer_quality_enabled
                and state.request.target_stage is None
                else "skipped"
            )
            quality_score = None
        else:
            quality_status = "passed" if selected_decision.passed else "insufficient"
            quality_score = selected_decision.score
        comparison: JsonObject = {
            "baseline_version": runtime.config.answer_quality_baseline_version,
            "threshold": threshold,
            "enabled_for_run": quality_enabled,
            "regeneration_triggered": regenerated_output is not None,
            "selected_variant": selected_variant,
            "selection_reason": selection_reason,
            "retrieval_expansion": retrieval_expansion,
            "initial": _answer_variant_snapshot(
                initial_output,
                initial_evaluation,
                initial_decision,
            ),
            "regenerated": None
            if regenerated_output is None
            else _answer_variant_snapshot(
                regenerated_output,
                regenerated_evaluation,
                regenerated_decision,
            ),
            "evaluation_error": evaluation_error,
        }
        value: JsonObject = {
            "execution_status": "passed",
            "quality_status": quality_status,
            "score": quality_score,
            "summary": selected_output.summary,
            "action_plan": selected_output.action_plan,
            "caution": selected_output.caution,
            "token_usage": usage.model_dump(mode="json"),
            "execution_profile": "report_snapshot_only",
            "snapshot_bundle_hash": selected_bundle_hash,
            "tool_call_count": 0,
            "model_call_count": usage.model_calls,
            "answer_quality_comparison": comparison,
        }
        updated = state.model_copy(update={"report_draft": value})
        return StageSnapshotEnvelope(
            stage_name="report_draft",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(
                force_review=not generation_available
                or (selected_decision is not None and not selected_decision.passed)
                or (quality_enabled and selected_decision is None),
            ),
        )

    return execute


def _report_bundle(
    state: AgentV2State,
    evidence: JsonObject,
) -> ReportDraftSnapshotBundle:
    bundle_data: JsonObject = {
        "ml_validation": evidence.get("ml_validation") or {},
        "weather_context": evidence.get("weather_context") or {},
        "rag_retrieval": evidence.get("rag_retrieval") or {},
        "rag_interpretation": evidence.get("rag_interpretation") or {},
        "fault_analysis": evidence.get("fault_analysis") or {},
        "higher_model_reassessment": evidence.get("higher_model_reassessment") or {},
        "parent_disposition": evidence.get("parent_disposition") or {},
    }
    return ReportDraftSnapshotBundle(
        run_id=state.request.run_id,
        root_run_id=state.request.run_id,
        target_stage=state.request.target_stage,
        source_input_hash=state.request.input_hash,
        bundle_hash=canonical_json_hash(bundle_data),
        stages=bundle_data,
    )


async def _expanded_rag_for_revision(
    runtime: AgentRuntime,
    state: AgentV2State,
) -> tuple[JsonObject, JsonObject]:
    candidate_top_k = max(
        runtime.config.rag_top_k,
        runtime.config.rag_expanded_top_k,
        runtime.config.rag_max_top_k,
    )
    candidate_top_k = max(1, min(candidate_top_k, 20))
    snapshot = await runtime.rag.search(
        RagEvidenceRequest(
            card_id=state.request.card_id,
            source_input=state.request.source_input,
            top_k=candidate_top_k,
        )
    )
    reranked, metadata = rerank_retrieval(
        snapshot.retrieval,
        state.request.source_input,
        limit=runtime.config.rag_top_k,
    )
    raw_chunks = reranked.get("chunks")
    chunks = (
        [item for item in raw_chunks if isinstance(item, dict)]
        if isinstance(raw_chunks, list)
        else []
    )
    if not chunks:
        raise AgentDependencyError(
            service="rag",
            detail="expanded retrieval returned no usable evidence",
        )
    quality, reasons = evaluate_retrieval_quality(
        reranked,
        quality_enabled=True,
        jsonl_min_top_score=runtime.config.rag_jsonl_min_top_score,
        jsonl_min_unique_matches=runtime.config.rag_jsonl_min_unique_matches,
    )
    references: JsonObject = {
        "technical_standards": [
            {
                "chunk_id": chunk.get("chunk_id"),
                "document_title": chunk.get("document_title"),
                "source_file": chunk.get("source_file"),
                "curated_file": chunk.get("curated_file"),
                "page_start": chunk.get("page_start"),
                "page_end": chunk.get("page_end"),
                "download_url": chunk.get("download_url"),
            }
            for chunk in chunks
        ],
        "regulations": [],
    }
    raw_attempts = state.rag_retrieval.get("retrieval_attempts")
    previous_attempts = raw_attempts if isinstance(raw_attempts, list) else []
    expanded_rag: JsonObject = {
        **state.rag_retrieval,
        "execution_status": quality.execution_status,
        "quality_status": quality.quality_status,
        "score": quality.score,
        "retrieval": reranked,
        "references": references,
        "status": snapshot.status,
        "quality_reasons": list(reasons),
        "retrieval_attempts": [
            *previous_attempts,
            {
                "top_k": candidate_top_k,
                "result_count": metadata["candidate_count"],
                "selected_count": metadata["selected_count"],
                "quality_status": quality.quality_status,
                "score": quality.score,
                "reasons": list(reasons),
                "trigger": "initial_answer_retrieval_insufficient",
            },
        ],
        "broadened": True,
        "auto_expanded": True,
    }
    return expanded_rag, {
        **metadata,
        "candidate_top_k": candidate_top_k,
        "quality_status": quality.quality_status,
        "quality_score": quality.score,
    }


async def _evaluate_once(
    runtime: AgentRuntime,
    *,
    run_id: str,
    source_input: JsonObject,
    evidence_context: JsonObject,
    answer: OpsAgentOutput,
    usage: TokenUsage,
    threshold: float,
) -> tuple[
    AnswerQualityEvaluation,
    AnswerQualityDecision,
]:
    evaluation = await runtime.evaluate_answer_quality(
        run_id=run_id,
        source_input=source_input,
        evidence_context=evidence_context,
        answer=answer,
        usage=usage,
    )
    return evaluation, evaluate_against_baseline(evaluation, threshold=threshold)


def _answer_variant_snapshot(
    output: OpsAgentOutput,
    evaluation: AnswerQualityEvaluation | None,
    decision: AnswerQualityDecision | None,
) -> JsonObject:
    return {
        "answer": output.model_dump(mode="json"),
        "evaluation": None
        if evaluation is None
        else evaluation.model_dump(mode="json"),
        "score": None if decision is None else decision.score,
        "passed": None if decision is None else decision.passed,
        "hard_gate_failed": None if decision is None else decision.hard_gate_failed,
        "reasons": [] if decision is None else list(decision.reasons),
    }


def _fidelity() -> StageAdapter:
    async def execute(state: AgentV2State) -> StageSnapshotEnvelope:
        has_report = all(
            isinstance(state.report_draft.get(field), str) and state.report_draft[field]
            for field in ("summary", "action_plan", "caution")
        )
        draft_quality = state.report_draft.get("quality_status")
        comparison = state.report_draft.get("answer_quality_comparison")
        quality_evaluated = (
            isinstance(comparison, dict)
            and comparison.get("enabled_for_run") is True
        )
        selected_score = state.report_draft.get("score")
        quality_failed = draft_quality in {"insufficient", "unavailable"}
        value: JsonObject = {
            "execution_status": "passed" if has_report else "failed",
            "quality_status": (
                draft_quality
                if has_report and quality_evaluated and isinstance(draft_quality, str)
                else "passed" if has_report else "insufficient"
            ),
            "score": (
                float(selected_score)
                if quality_evaluated and isinstance(selected_score, int | float)
                else 100.0 if has_report else None
            ),
            "judge": "answer_quality_baseline" if quality_evaluated else "deterministic",
        }
        updated = state.model_copy(update={"report_fidelity": value})
        return StageSnapshotEnvelope(
            stage_name="report_fidelity",
            data=updated.model_dump(mode="json"),
            control=StageControlEnvelope(force_review=not has_report or quality_failed),
        )

    return execute
