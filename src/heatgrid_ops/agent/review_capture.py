from __future__ import annotations

from hashlib import sha256
import json
from math import isfinite
from typing import TYPE_CHECKING, Final

from pydantic import ValidationError

from heatgrid_ops.agent.diagnostics import (
    DIAGNOSTIC_INPUT_TOKEN_LIMIT,
    DIAGNOSTIC_OUTPUT_TOKEN_LIMIT,
)
from heatgrid_ops.agent.models import JsonObject, JsonValue
from heatgrid_ops.agent.review_models import (
    AgentRunReviewCaptureSource,
    AgentRunReviewSnapshotV1,
    ReviewComponentResult,
    ReviewDiagnosticHypothesis,
    ReviewDiagnosticSnapshot,
    ReviewCaptureEvidenceSnapshot,
    ReviewCaptureSourceCardSnapshot,
    ReviewFinalResultSnapshot,
    ReviewModelVerificationSnapshot,
    ReviewOpsAgentOutput,
    ReviewProvenanceSnapshot,
    ReviewWeatherSnapshot,
)
from heatgrid_ops.agent.run_models import AgentRunResult

if TYPE_CHECKING:
    from heatgrid_ops.agent.state import AgentState


_MAX_EXCERPT_CHARS: Final = 1_600


def build_review_capture_source(
    state: AgentState,
    result: AgentRunResult,
) -> AgentRunReviewCaptureSource:
    if result.run_id != state.request.run_id:
        raise RuntimeError("review capture run_id does not match graph state")
    assessment = state.loop.assessment
    if assessment is None:
        raise RuntimeError("evidence assessment is missing")
    return AgentRunReviewCaptureSource(
        run_id=state.request.run_id,
        result=_final_result(result),
        loop_count=state.loop.iteration,
        handling_reason=assessment.rationale[:1000],
        diagnostic=_diagnostic(state),
        model_verification=_model_verification(state),
        weather=_weather(state.evidence.external_context),
        evidence=_evidence(state.evidence.external_context),
        source_card=_source_card(state),
    )


def try_build_review_capture_source(
    state: AgentState,
    result: AgentRunResult,
) -> AgentRunReviewCaptureSource | None:
    try:
        return build_review_capture_source(state, result)
    except (RuntimeError, ValidationError):
        return None


def canonical_review_json(
    value: AgentRunReviewCaptureSource | AgentRunReviewSnapshotV1,
) -> str:
    payload = value.model_dump(mode="json")
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def review_content_hash(
    value: AgentRunReviewCaptureSource | AgentRunReviewSnapshotV1,
) -> str:
    return sha256(canonical_review_json(value).encode("utf-8")).hexdigest()


def _final_result(result: AgentRunResult) -> ReviewFinalResultSnapshot:
    match result.status:
        case "completed":
            status = "completed"
        case "failed":
            status = "failed"
        case "queued" | "running":
            raise RuntimeError("review capture requires a terminal run result")
    output = result.ops_output
    return ReviewFinalResultSnapshot(
        status=status,
        agent_mode=result.agent_mode,
        ops_output=None
        if output is None
        else ReviewOpsAgentOutput(
            summary=output.summary,
            action_plan=output.action_plan,
            caution=output.caution,
        ),
        error=result.error,
    )


def _diagnostic(state: AgentState) -> ReviewDiagnosticSnapshot:
    summary = state.evidence.diagnostic_summary
    if summary is None:
        return ReviewDiagnosticSnapshot(status="not_triggered")
    return ReviewDiagnosticSnapshot(
        trigger="fault_diagnosis:v1" if state.loop.diagnostic_attempted else None,
        status=summary.status,
        hypotheses=tuple(
            ReviewDiagnosticHypothesis(
                hypothesis_id=item.hypothesis_id[:200],
                title=item.title[:500],
                rationale=item.rationale[:2000],
                evidence_ids=tuple(item.evidence_ids),
                confidence=item.confidence,
            )
            for item in summary.hypotheses
        ),
        attempts=summary.attempts,
        input_tokens=summary.input_tokens,
        output_tokens=summary.output_tokens,
        input_token_limit=DIAGNOSTIC_INPUT_TOKEN_LIMIT,
        output_token_limit=DIAGNOSTIC_OUTPUT_TOKEN_LIMIT,
        deadline_seconds=60,
        fallback_reason=_bounded(summary.fallback_reason, 1000),
    )


def _model_verification(state: AgentState) -> ReviewModelVerificationSnapshot | None:
    verification = state.evidence.model_verification
    if verification is None:
        return None
    return ReviewModelVerificationSnapshot(
        status=verification.status,
        agreement=verification.agreement,
        component_results=tuple(
            ReviewComponentResult(component=name[:200], agreement=agreement)
            for name, agreement in sorted(verification.component_agreement.items())
            if name
        ),
        stored_score=_finite_optional(verification.stored_priority_score),
        current_score=_finite_optional(verification.priority_score),
        score_delta=_finite_optional(verification.priority_score_delta),
        reason=("; ".join(verification.reasons) or verification.status)[:1000],
    )


def _weather(external_context: JsonObject) -> ReviewWeatherSnapshot | None:
    weather = _mapping(external_context.get("weather"))
    provenance = _provenance(weather.get("provenance"))
    status = _string(weather.get("status"))
    humidity = _number(_first(weather, "humidity_percent", "humidity"))
    precipitation = _number(weather.get("precipitation_mm"))
    wind_speed = _number(_first(weather, "wind_speed_mps", "wind_speed"))
    if (
        status is None
        or provenance is None
        or (humidity is not None and not 0.0 <= humidity <= 100.0)
        or (precipitation is not None and precipitation < 0.0)
        or (wind_speed is not None and wind_speed < 0.0)
    ):
        return None
    return ReviewWeatherSnapshot(
        status=status[:120],
        observed_at=_bounded(
            _string(weather.get("observed_at") or weather.get("base_time")), 120
        ),
        temperature_c=_number(_first(weather, "temperature_c", "temperature")),
        humidity_percent=humidity,
        precipitation_mm=precipitation,
        wind_speed_mps=wind_speed,
        provenance=provenance,
    )


def _evidence(
    external_context: JsonObject,
) -> tuple[ReviewCaptureEvidenceSnapshot, ...]:
    retrieval = _mapping(external_context.get("retrieval"))
    values = retrieval.get("chunks")
    if not isinstance(values, list):
        return ()
    snapshots = tuple(
        snapshot
        for value in values
        if isinstance(value, dict)
        and (snapshot := _evidence_item(value)) is not None
    )
    return tuple(
        sorted(
            snapshots,
            key=lambda item: (-item.score, item.evidence_id, item.model_dump_json()),
        )
    )


def _evidence_item(value: JsonObject) -> ReviewCaptureEvidenceSnapshot | None:
    evidence_id = _string(value.get("chunk_id") or value.get("evidence_id"))
    provenance = _provenance(value.get("provenance"))
    direct_source = _string(value.get("source_file") or value.get("source"))
    source = direct_source or (None if provenance is None else provenance.source)
    title = _string(value.get("document_title") or value.get("title"))
    excerpt = _string(value.get("text") or value.get("content"))
    score = _number(value.get("score"))
    if (
        not evidence_id
        or not source
        or not title
        or not excerpt
        or score is None
        or score < 0.0
    ):
        return None
    document_type = (
        "operator_manual_evidence"
        if value.get("document_type") == "operator_manual_evidence"
        else "internal_rag"
    )
    return ReviewCaptureEvidenceSnapshot(
        evidence_id=evidence_id[:200],
        document_type=document_type,
        source_owner=_bounded(_string(value.get("source_owner")), 200),
        source=source[:500],
        title=title[:500],
        section=_bounded(
            _string(value.get("section") or value.get("section_title")), 500
        ),
        score=score,
        excerpt=excerpt[:_MAX_EXCERPT_CHARS],
        provenance=provenance,
    )


def _source_card(state: AgentState) -> ReviewCaptureSourceCardSnapshot:
    source = state.request.source_input
    priority_context = _mapping(source.get("priority_context"))
    card = _mapping(priority_context.get("card"))
    priority = _mapping(priority_context.get("priority"))
    explanation = _mapping(priority_context.get("explanation"))
    window = _mapping(_mapping(source.get("raw_context")).get("window"))
    return ReviewCaptureSourceCardSnapshot(
        card_id=state.request.card_id,
        substation_id=_integer(window.get("substation_id")),
        manufacturer_id=_bounded(_string(window.get("manufacturer_id")), 200),
        priority_level=_bounded(_string(priority.get("priority_level")), 120),
        status=_bounded(_string(card.get("status")), 120),
        review_required=bool(card.get("review_required")),
        reason=_bounded(
            _string(
                explanation.get("why_reason")
                or card.get("why_reason")
                or card.get("reason")
            ),
            1000,
        ),
    )


def _provenance(value: JsonValue | None) -> ReviewProvenanceSnapshot | None:
    raw = _mapping(value)
    source = _string(raw.get("source") or raw.get("source_path"))
    if not source:
        return None
    return ReviewProvenanceSnapshot(
        source=source[:500],
        source_owner=_bounded(_string(raw.get("source_owner")), 200),
        snapshot_id=_bounded(_string(raw.get("snapshot_id")), 200),
        retrieval_id=_bounded(_string(raw.get("retrieval_id")), 200),
        document_id=_bounded(_string(raw.get("document_id")), 200),
        chunk_id=_bounded(_string(raw.get("chunk_id")), 200),
    )


def _mapping(value: JsonValue | None) -> JsonObject:
    return value if isinstance(value, dict) else {}


def _string(value: JsonValue | None) -> str | None:
    return value if isinstance(value, str) and value else None


def _integer(value: JsonValue | None) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _number(value: JsonValue | None) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if isfinite(number) else None


def _finite_optional(value: float | None) -> float | None:
    return value if value is not None and isfinite(value) else None


def _first(mapping: JsonObject, primary: str, fallback: str) -> JsonValue | None:
    value = mapping.get(primary)
    return mapping.get(fallback) if value is None else value


def _bounded(value: str | None, maximum: int) -> str | None:
    return None if value is None else value[:maximum]
