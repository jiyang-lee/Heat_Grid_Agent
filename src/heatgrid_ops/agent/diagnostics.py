from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from time import monotonic
from typing import Literal, Protocol

from anyio import fail_after
from pydantic import BaseModel, ConfigDict, Field

from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.helpers import to_json
from heatgrid_ops.agent.models import JsonObject, TokenCall


DIAGNOSTIC_INPUT_TOKEN_LIMIT = 3_000
DIAGNOSTIC_OUTPUT_TOKEN_LIMIT = 1_000
DIAGNOSTIC_TOTAL_TOKEN_LIMIT = 4_000
DIAGNOSTIC_DEADLINE_SECONDS = 60.0
DIAGNOSTIC_FIRST_ATTEMPT_SECONDS = 45.0
DIAGNOSTIC_RETRY_SECONDS = 15.0

DIAGNOSTIC_SYSTEM_PROMPT = (
    "Analyze the supplied read-only HeatGrid snapshots. Return up to three fault "
    "hypotheses grounded only in cited evidence IDs. Do not make a final decision, "
    "prescribe an action, or provide a recommendation."
)


class FrozenDiagnosticModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DiagnosticCardSnapshot(FrozenDiagnosticModel):
    card_id: str
    substation_uid: str
    substation_id: int | None = None
    manufacturer_id: str | None = None
    priority_level: str
    status: str | None = None
    review_required: bool
    reason: str


class DiagnosticModelSnapshot(FrozenDiagnosticModel):
    status: str
    agreement: bool | None = None
    component_results: dict[str, bool] = Field(default_factory=dict)
    stored_score: float | None = None
    current_score: float | None = None
    score_delta: float | None = None
    reason: str


class DiagnosticWeatherSnapshot(FrozenDiagnosticModel):
    status: str
    observed_at: str | None = None
    temperature_c: float | None = None
    humidity_percent: float | None = None
    precipitation_mm: float | None = None
    wind_speed_mps: float | None = None
    provenance: JsonObject = Field(default_factory=dict)


class DiagnosticRagChunk(FrozenDiagnosticModel):
    evidence_id: str
    source: str
    title: str
    section: str | None = None
    excerpt: str
    score: float = 0.0


class DiagnosticWorkerInput(FrozenDiagnosticModel):
    run_id: str
    task_key: Literal["fault_diagnosis:v1"] = "fault_diagnosis:v1"
    card: DiagnosticCardSnapshot
    model: DiagnosticModelSnapshot
    weather: DiagnosticWeatherSnapshot
    rag_chunks: list[DiagnosticRagChunk] = Field(default_factory=list, max_length=5)


class DiagnosticHypothesis(FrozenDiagnosticModel):
    hypothesis_id: str
    title: str
    rationale: str
    evidence_ids: list[str] = Field(min_length=1, max_length=8)
    confidence: float = Field(ge=0.0, le=1.0)


class DiagnosticWorkerOutput(FrozenDiagnosticModel):
    hypotheses: list[DiagnosticHypothesis] = Field(min_length=1, max_length=3)


class DiagnosticModelResult(FrozenDiagnosticModel):
    output: DiagnosticWorkerOutput
    calls: list[TokenCall] = Field(default_factory=list)


class DiagnosticModelPort(Protocol):
    async def diagnose(
        self, request: DiagnosticWorkerInput
    ) -> DiagnosticModelResult: ...


class DiagnosticSummary(FrozenDiagnosticModel):
    status: Literal[
        "completed",
        "failed",
        "timeout",
        "invalid",
        "budget_exceeded",
    ]
    hypotheses: list[DiagnosticHypothesis] = Field(default_factory=list, max_length=3)
    attempts: int = Field(ge=0, le=2)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    fallback_reason: str | None = None


class DiagnosticBudgetReservation(FrozenDiagnosticModel):
    reservation_id: str | None = None
    granted: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DiagnosticExecution:
    summary: DiagnosticSummary
    calls: list[TokenCall]


@dataclass(frozen=True, slots=True)
class DiagnosticWorker:
    model: DiagnosticModelPort

    async def run(self, request: DiagnosticWorkerInput) -> DiagnosticExecution:
        input_tokens = estimate_diagnostic_input_tokens(request)
        if input_tokens > DIAGNOSTIC_INPUT_TOKEN_LIMIT:
            return _fallback(
                "budget_exceeded",
                attempts=0,
                input_tokens=input_tokens,
                reason="diagnostic_input_exceeds_3000_tokens",
            )

        deadline = monotonic() + DIAGNOSTIC_DEADLINE_SECONDS
        last_status: Literal["failed", "timeout", "invalid"] = "failed"
        last_reason = "diagnostic_model_failed"
        for attempt in (1, 2):
            total_input_tokens = input_tokens * attempt
            if total_input_tokens > DIAGNOSTIC_TOTAL_TOKEN_LIMIT:
                return _fallback(
                    "budget_exceeded",
                    attempts=attempt - 1,
                    input_tokens=input_tokens * (attempt - 1),
                    reason="diagnostic_retry_exceeds_4000_token_budget",
                )
            remaining = deadline - monotonic()
            if remaining <= 0:
                return _fallback(
                    "timeout",
                    attempts=attempt - 1,
                    input_tokens=input_tokens,
                    reason="diagnostic_deadline_exhausted",
                )
            timeout = min(
                remaining,
                DIAGNOSTIC_FIRST_ATTEMPT_SECONDS
                if attempt == 1
                else DIAGNOSTIC_RETRY_SECONDS,
            )
            try:
                with fail_after(timeout):
                    result = await self.model.diagnose(request)
                output_tokens = _output_tokens(result)
                observed_input_tokens = sum(call.input_tokens for call in result.calls)
                total_input_tokens = max(total_input_tokens, observed_input_tokens)
                if total_input_tokens > DIAGNOSTIC_INPUT_TOKEN_LIMIT * attempt:
                    last_status = "invalid"
                    last_reason = "diagnostic_observed_input_exceeds_budget"
                    continue
                if output_tokens > DIAGNOSTIC_OUTPUT_TOKEN_LIMIT:
                    last_status = "invalid"
                    last_reason = "diagnostic_output_exceeds_1000_tokens"
                    continue
                if total_input_tokens + output_tokens > DIAGNOSTIC_TOTAL_TOKEN_LIMIT:
                    return _fallback(
                        "budget_exceeded",
                        attempts=attempt,
                        input_tokens=total_input_tokens,
                        reason="diagnostic_total_exceeds_4000_tokens",
                    )
                if not _citations_are_valid(request, result.output):
                    last_status = "invalid"
                    last_reason = "diagnostic_output_has_unknown_evidence_ids"
                    continue
                return DiagnosticExecution(
                    summary=DiagnosticSummary(
                        status="completed",
                        hypotheses=result.output.hypotheses[:3],
                        attempts=attempt,
                        input_tokens=total_input_tokens,
                        output_tokens=output_tokens,
                    ),
                    calls=result.calls,
                )
            except TimeoutError:
                last_status = "timeout"
                last_reason = "diagnostic_model_timeout"
            except AgentDependencyError as exc:
                last_status = "failed"
                last_reason = f"diagnostic_model_failed:{type(exc).__name__}"
        return _fallback(
            last_status,
            attempts=2,
            input_tokens=input_tokens * 2,
            reason=last_reason,
        )


def estimate_diagnostic_input_tokens(request: DiagnosticWorkerInput) -> int:
    schema = DiagnosticWorkerOutput.model_json_schema()
    chars = (
        len(DIAGNOSTIC_SYSTEM_PROMPT)
        + len(to_json(schema))
        + len(request.model_dump_json())
    )
    return ceil(chars / 4)


def _output_tokens(result: DiagnosticModelResult) -> int:
    observed = sum(call.output_tokens for call in result.calls)
    estimated = ceil(len(result.output.model_dump_json()) / 4)
    return max(observed, estimated)


def _citations_are_valid(
    request: DiagnosticWorkerInput,
    output: DiagnosticWorkerOutput,
) -> bool:
    evidence_ids = {chunk.evidence_id for chunk in request.rag_chunks}
    return all(
        set(hypothesis.evidence_ids).issubset(evidence_ids)
        for hypothesis in output.hypotheses
    )


def _fallback(
    status: Literal["failed", "timeout", "invalid", "budget_exceeded"],
    *,
    attempts: int,
    input_tokens: int,
    reason: str,
) -> DiagnosticExecution:
    return DiagnosticExecution(
        summary=DiagnosticSummary(
            status=status,
            attempts=attempts,
            input_tokens=input_tokens,
            output_tokens=0,
            fallback_reason=reason,
        ),
        calls=[],
    )
