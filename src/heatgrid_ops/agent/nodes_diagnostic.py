from __future__ import annotations

from heatgrid_ops.agent.diagnostics import (
    DIAGNOSTIC_TOTAL_TOKEN_LIMIT,
    DiagnosticCardSnapshot,
    DiagnosticExecution,
    DiagnosticModelSnapshot,
    DiagnosticSummary,
    DiagnosticWeatherSnapshot,
    DiagnosticWorker,
    DiagnosticWorkerInput,
    DiagnosticRagChunk,
    estimate_diagnostic_input_tokens,
)
from heatgrid_ops.agent.models import JsonObject, JsonValue
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_audit import record_decision
from heatgrid_ops.agent.state import AgentState, AgentStateUpdate


async def run_diagnostic_worker(
    context: AgentNodeContext,
    state: AgentState,
) -> AgentStateUpdate:
    await record_decision(context, state, "fault_diagnosis:v1")
    request = build_diagnostic_input(state)
    execution = await _execute_worker(context, state, request)
    summary = execution.summary
    await context.audit.record_event(
        state.request.run_id,
        "diagnostic_worker_completed",
        "read-only diagnostic worker completed",
        {
            "task_key": request.task_key,
            "status": summary.status,
            "attempts": summary.attempts,
            "input_tokens": summary.input_tokens,
            "output_tokens": summary.output_tokens,
            "hypothesis_count": len(summary.hypotheses),
            "fallback_reason": summary.fallback_reason,
        },
    )
    return {
        "evidence": state.evidence.model_copy(
            update={
                "diagnostic_summary": summary,
                "diagnostic_calls": execution.calls,
            }
        ),
        "loop": state.loop.model_copy(
            update={"diagnostic_attempted": True, "force_review": True}
        ),
    }


async def _execute_worker(
    context: AgentNodeContext,
    state: AgentState,
    request: DiagnosticWorkerInput,
) -> DiagnosticExecution:
    budget = context.budget
    model = context.runtime.diagnostic_model
    input_tokens = estimate_diagnostic_input_tokens(request)
    if budget is None or model is None:
        return _unavailable_execution(input_tokens, "diagnostic_capability_unavailable")
    reservation = await budget.reserve_diagnostic(
        state.request.run_id,
        DIAGNOSTIC_TOTAL_TOKEN_LIMIT,
    )
    if not reservation.granted or reservation.reservation_id is None:
        return _unavailable_execution(
            input_tokens,
            reservation.reason or "diagnostic_budget_unavailable",
            status="budget_exceeded",
        )
    execution = await DiagnosticWorker(model).run(request)
    tokens_used = min(
        DIAGNOSTIC_TOTAL_TOKEN_LIMIT,
        execution.summary.input_tokens + execution.summary.output_tokens,
    )
    await budget.finish_diagnostic(
        reservation.reservation_id,
        tokens_used=tokens_used,
        model_called=execution.summary.attempts > 0,
    )
    return execution


def build_diagnostic_input(state: AgentState) -> DiagnosticWorkerInput:
    source = state.request.source_input
    priority_context = _mapping(source.get("priority_context"))
    card = _mapping(priority_context.get("card"))
    priority = _mapping(priority_context.get("priority"))
    raw_context = _mapping(source.get("raw_context"))
    window = _mapping(raw_context.get("window"))
    external = state.evidence.external_context
    weather = _mapping(external.get("weather"))
    retrieval = _mapping(external.get("retrieval"))
    verification = state.evidence.model_verification

    return DiagnosticWorkerInput(
        run_id=state.request.run_id,
        card=DiagnosticCardSnapshot(
            card_id=state.request.card_id,
            substation_id=_integer(window.get("substation_id")),
            manufacturer_id=_string(window.get("manufacturer_id")),
            priority_level=str(priority.get("priority_level") or "unknown").lower(),
            status=_string(card.get("status")),
            review_required=bool(card.get("review_required")),
            reason=str(card.get("why_reason") or card.get("reason") or "unspecified"),
        ),
        model=DiagnosticModelSnapshot(
            status="unavailable" if verification is None else verification.status,
            agreement=None if verification is None else verification.agreement,
            component_results={}
            if verification is None
            else verification.component_agreement,
            stored_score=None
            if verification is None
            else verification.stored_priority_score,
            current_score=None if verification is None else verification.priority_score,
            score_delta=None
            if verification is None
            else verification.priority_score_delta,
            reason="model verification unavailable"
            if verification is None
            else "; ".join(verification.reasons) or verification.status,
        ),
        weather=DiagnosticWeatherSnapshot(
            status=str(weather.get("status") or "unavailable"),
            observed_at=_string(weather.get("observed_at") or weather.get("base_time")),
            temperature_c=_number(_first(weather, "temperature_c", "temperature")),
            humidity_percent=_number(_first(weather, "humidity_percent", "humidity")),
            precipitation_mm=_number(weather.get("precipitation_mm")),
            wind_speed_mps=_number(_first(weather, "wind_speed_mps", "wind_speed")),
            provenance=_mapping(weather.get("provenance")),
        ),
        rag_chunks=_rag_chunks(retrieval),
    )


def _rag_chunks(retrieval: JsonObject) -> list[DiagnosticRagChunk]:
    values = retrieval.get("chunks")
    if not isinstance(values, list):
        return []
    chunks: list[DiagnosticRagChunk] = []
    for index, value in enumerate(values[:5]):
        if not isinstance(value, dict):
            continue
        chunks.append(
            DiagnosticRagChunk(
                evidence_id=str(value.get("chunk_id") or f"rag-{index + 1}"),
                source=str(value.get("source_file") or value.get("source") or "rag"),
                title=str(
                    value.get("document_title") or value.get("title") or "untitled"
                ),
                section=_string(value.get("section")),
                excerpt=str(value.get("text") or value.get("content") or "")[:4000],
                score=_number(value.get("score")) or 0.0,
            )
        )
    return chunks


def _unavailable_execution(
    input_tokens: int,
    reason: str,
    *,
    status: str = "failed",
) -> DiagnosticExecution:
    return DiagnosticExecution(
        summary=DiagnosticSummary.model_validate(
            {
                "status": status,
                "attempts": 0,
                "input_tokens": input_tokens,
                "output_tokens": 0,
                "fallback_reason": reason,
            }
        ),
        calls=[],
    )


def _mapping(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) else None


def _integer(value: JsonValue | None) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: JsonValue | None) -> float | None:
    return (
        float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
        else None
    )


def _first(mapping: JsonObject, primary: str, fallback: str) -> JsonValue | None:
    value = mapping.get(primary)
    return mapping.get(fallback) if value is None else value
