from __future__ import annotations

from pathlib import Path

import orjson

from heatgrid_ops.agent.diagnostic_input import prepare_diagnostic_input
from heatgrid_ops.agent.diagnostics import (
    DiagnosticCardSnapshot,
    DiagnosticModelSnapshot,
    DiagnosticRagChunk,
    DiagnosticWeatherSnapshot,
    DiagnosticWorkerInput,
)


def test_case_a_input_under_limit_is_ready_for_model() -> None:
    prepared = prepare_diagnostic_input(_request([("rag-1", 0.9, "brief reference")]))

    assert prepared.request is not None
    assert prepared.after_tokens <= 3_000
    assert prepared.selected_evidence_ids == ("rag-1",)


def test_case_b_oversized_rag_is_compacted_deterministically() -> None:
    prepared = prepare_diagnostic_input(
        _request(
            [
                ("rag-b", 0.8, "b" * 8_000),
                ("rag-c", 0.8, "c" * 8_000),
                ("rag-a", 0.95, "a" * 8_000),
                ("rag-d", 0.7, "d" * 8_000),
                ("rag-e", 0.6, "e" * 8_000),
            ]
        )
    )

    assert prepared.request is not None
    assert prepared.before_tokens > 3_000
    assert prepared.after_tokens <= 3_000
    assert prepared.selected_evidence_ids == (
        "rag-a",
        "rag-b",
        "rag-c",
        "rag-d",
        "rag-e",
    )
    assert all(len(chunk.excerpt) <= 1_600 for chunk in prepared.request.rag_chunks)


def test_case_c_minimum_input_over_limit_skips_model() -> None:
    prepared = prepare_diagnostic_input(
        _request([("rag-1", 0.9, "reference")], reason="x" * 20_000)
    )

    assert prepared.request is None
    assert prepared.after_tokens > 3_000
    assert prepared.fallback_reason == "diagnostic_minimum_input_exceeds_3000_tokens"


def test_missing_weather_or_citable_rag_skips_model() -> None:
    missing_weather = prepare_diagnostic_input(
        _request([("rag-1", 0.9, "reference")], weather_status="unavailable")
    )
    missing_rag = prepare_diagnostic_input(_request([]))

    assert missing_weather.fallback_reason == "diagnostic_weather_unavailable"
    assert missing_rag.fallback_reason == "diagnostic_citable_rag_unavailable"


def test_a_b_c_measurements_match_fixture() -> None:
    fixture = orjson.loads(
        (
            Path(__file__).parent / "fixtures" / "diagnostic_input_cases.json"
        ).read_bytes()
    )["cases"]
    prepared = {
        "A_under_limit": prepare_diagnostic_input(
            _request([("rag-1", 0.9, "brief reference")])
        ),
        "B_compactable": prepare_diagnostic_input(
            _request(
                [
                    ("rag-b", 0.8, "b" * 8_000),
                    ("rag-c", 0.8, "c" * 8_000),
                    ("rag-a", 0.95, "a" * 8_000),
                    ("rag-d", 0.7, "d" * 8_000),
                    ("rag-e", 0.6, "e" * 8_000),
                ]
            )
        ),
        "C_minimum_over_limit": prepare_diagnostic_input(
            _request([("rag-1", 0.9, "reference")], reason="x" * 20_000)
        ),
    }

    for name, result in prepared.items():
        expected = fixture[name]
        assert result.before_tokens == expected["input_tokens_before"]
        assert result.after_tokens == expected["input_tokens_after"]
        assert (result.request is not None) is expected["model_called"]
        assert result.fallback_reason == expected["fallback_reason"]
        assert list(result.selected_evidence_ids) == expected["selected_evidence_ids"]


def _request(
    chunks: list[tuple[str, float, str]],
    *,
    reason: str = "temperature-flow mismatch",
    weather_status: str = "available",
) -> DiagnosticWorkerInput:
    return DiagnosticWorkerInput(
        run_id="run-1",
        card=DiagnosticCardSnapshot(
            card_id="card-1",
            substation_uid="00000000-0000-0000-0000-000000000031",
            substation_id=31,
            manufacturer_id="manufacturer-1",
            priority_level="high",
            status="open",
            review_required=False,
            reason=reason,
        ),
        model=DiagnosticModelSnapshot(
            status="verified",
            agreement=False,
            component_results={"risk": False},
            stored_score=0.6,
            current_score=0.8,
            score_delta=0.2,
            reason="risk score changed",
        ),
        weather=DiagnosticWeatherSnapshot(
            status=weather_status,
            observed_at="2026-07-14T12:00:00+09:00",
            temperature_c=30.0,
            humidity_percent=70.0,
            precipitation_mm=0.0,
            wind_speed_mps=1.5,
            provenance={"source": "weather_snapshot"},
        ),
        rag_chunks=[
            DiagnosticRagChunk(
                evidence_id=evidence_id,
                source="manual.pdf",
                title="Operations manual",
                section="Heat exchanger",
                excerpt=excerpt,
                score=score,
            )
            for evidence_id, score, excerpt in chunks
        ],
    )
