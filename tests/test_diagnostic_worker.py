from __future__ import annotations

import pytest
from pydantic import ValidationError

from heatgrid_ops.agent.diagnostics import (
    DiagnosticCardSnapshot,
    DiagnosticHypothesis,
    DiagnosticModelResult,
    DiagnosticModelSnapshot,
    DiagnosticRagChunk,
    DiagnosticWeatherSnapshot,
    DiagnosticWorker,
    DiagnosticWorkerInput,
    DiagnosticWorkerOutput,
)
from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.models import TokenCall


class SuccessfulDiagnosticModel:
    def __init__(self) -> None:
        self.calls = 0

    async def diagnose(self, request: DiagnosticWorkerInput) -> DiagnosticModelResult:
        self.calls += 1
        return DiagnosticModelResult(
            output=DiagnosticWorkerOutput(
                hypotheses=[
                    DiagnosticHypothesis(
                        hypothesis_id="hypothesis-1",
                        title="Heat exchanger drift",
                        rationale="The operating reference reports the same pattern.",
                        evidence_ids=[request.rag_chunks[0].evidence_id],
                        confidence=0.72,
                    )
                ]
            ),
            calls=[TokenCall(input_tokens=600, output_tokens=90, total_tokens=690)],
        )


class RetryDiagnosticModel(SuccessfulDiagnosticModel):
    async def diagnose(self, request: DiagnosticWorkerInput) -> DiagnosticModelResult:
        if self.calls == 0:
            self.calls += 1
            raise AgentDependencyError(service="llm", detail="transient")
        return await super().diagnose(request)


def test_diagnostic_output_rejects_decision_fields() -> None:
    with pytest.raises(ValidationError):
        DiagnosticHypothesis.model_validate(
            {
                "hypothesis_id": "hypothesis-1",
                "title": "Drift",
                "rationale": "Observed pattern",
                "evidence_ids": ["rag-1"],
                "confidence": 0.5,
                "decision": "replace component",
            }
        )


@pytest.mark.anyio
async def test_diagnostic_worker_returns_validated_hypotheses() -> None:
    model = SuccessfulDiagnosticModel()

    execution = await DiagnosticWorker(model).run(_request())

    assert execution.summary.status == "completed"
    assert execution.summary.attempts == 1
    assert len(execution.summary.hypotheses) == 1
    assert execution.summary.output_tokens <= 1_000
    assert model.calls == 1


@pytest.mark.anyio
async def test_diagnostic_worker_retries_once_within_budget() -> None:
    model = RetryDiagnosticModel()

    execution = await DiagnosticWorker(model).run(_request())

    assert execution.summary.status == "completed"
    assert execution.summary.attempts == 2
    assert execution.summary.input_tokens + execution.summary.output_tokens <= 4_000
    assert model.calls == 2


@pytest.mark.anyio
async def test_diagnostic_worker_skips_model_when_input_exceeds_limit() -> None:
    model = SuccessfulDiagnosticModel()
    request = _request(excerpt="x" * 20_000)

    execution = await DiagnosticWorker(model).run(request)

    assert execution.summary.status == "budget_exceeded"
    assert execution.summary.fallback_reason == "diagnostic_input_exceeds_3000_tokens"
    assert model.calls == 0


def _request(
    *, excerpt: str = "Repeated temperature and flow divergence."
) -> DiagnosticWorkerInput:
    return DiagnosticWorkerInput(
        run_id="run-1",
        card=DiagnosticCardSnapshot(
            card_id="card-1",
            substation_id=31,
            manufacturer_id="manufacturer-1",
            priority_level="high",
            status="open",
            review_required=False,
            reason="temperature-flow mismatch",
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
            status="available",
            observed_at="2026-07-14T12:00:00+09:00",
            temperature_c=30.0,
            humidity_percent=70.0,
            precipitation_mm=0.0,
            wind_speed_mps=1.5,
            provenance={"source": "weather_snapshot"},
        ),
        rag_chunks=[
            DiagnosticRagChunk(
                evidence_id="rag-1",
                source="manual.pdf",
                title="Operations manual",
                section="Heat exchanger",
                excerpt=excerpt,
                score=0.91,
            )
        ],
    )
