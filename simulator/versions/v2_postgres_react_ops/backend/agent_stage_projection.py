from __future__ import annotations

from agent_stage_repository import StageKind, StageName
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.quality import (
    StageQualityResult,
    ml_quality_result,
    rag_quality_result,
)
from heatgrid_ops.agent.state import ResultState


def project_stage_result(
    stage_name: StageName,
    result: ResultState,
    feature_flags: JsonObject,
) -> tuple[StageKind, StageQualityResult, JsonObject]:
    if stage_name == "ml_validation":
        verification = (
            None
            if result.review_capture_source is None
            else result.review_capture_source.model_verification
        )
        output = {} if verification is None else verification.model_dump(mode="json")
        quality = ml_quality_result(
            status="unavailable" if verification is None else verification.status,
            agreement=None if verification is None else verification.agreement,
        )
        return "quality", quality, output
    if stage_name == "weather_context":
        weather = (
            None
            if result.review_capture_source is None
            else result.review_capture_source.weather
        )
        if weather is None:
            return "quality", StageQualityResult("unavailable", "unavailable", None), {}
        populated = sum(
            value is not None
            for value in (
                weather.temperature_c,
                weather.humidity_percent,
                weather.precipitation_mm,
                weather.wind_speed_mps,
            )
        )
        score = 100.0 if populated == 4 and weather.provenance.source else 70.0
        status = "passed" if score == 100.0 else "partial"
        return (
            "quality",
            StageQualityResult("passed", status, score),
            weather.model_dump(mode="json"),
        )
    if stage_name in {"rag_retrieval", "rag_interpretation"}:
        evidence = (
            ()
            if result.review_capture_source is None
            else result.review_capture_source.evidence
        )
        quality = rag_quality_result(
            result_count=len(evidence),
            quality_enabled=bool(feature_flags.get("rag_quality")),
        )
        return "quality", quality, {
            "evidence": [item.model_dump(mode="json") for item in evidence]
        }
    if stage_name == "fault_analysis":
        diagnostic = (
            None
            if result.review_capture_source is None
            else result.review_capture_source.diagnostic
        )
        if diagnostic is None or diagnostic.status == "not_triggered":
            return "quality", StageQualityResult("skipped", "skipped", None), {}
        passed = diagnostic.status == "completed" and bool(diagnostic.hypotheses)
        quality = StageQualityResult(
            "passed" if passed else "failed",
            "passed" if passed else "insufficient",
            100.0 if passed else 0.0,
        )
        return "quality", quality, diagnostic.model_dump(mode="json")
    if stage_name == "higher_model_reassessment":
        return "orchestration", StageQualityResult("skipped", None, None), {
            "reason": "deterministic trigger not met"
        }
    if stage_name == "parent_disposition":
        return "orchestration", StageQualityResult("passed", None, None), {
            "handling_reason": (
                "unavailable"
                if result.review_capture_source is None
                else result.review_capture_source.handling_reason
            )
        }
    output = None if result.value is None else result.value.ops_output
    output_payload = {} if output is None else output.model_dump(mode="json")
    if stage_name == "report_draft":
        return (
            "orchestration",
            StageQualityResult("passed" if output is not None else "failed", None, None),
            output_payload,
        )
    complete = output is not None and all(
        (output.summary.strip(), output.action_plan.strip(), output.caution.strip())
    )
    return "quality", StageQualityResult(
        "passed" if complete else "failed",
        "passed" if complete else "insufficient",
        100.0 if complete else 0.0,
    ), output_payload
