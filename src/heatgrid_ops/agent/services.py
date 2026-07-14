from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from heatgrid_ops.agent.assessment import (
    EvidenceAssessment,
    assess_evidence,
    guard_llm_assessment,
)
from heatgrid_ops.agent.config import AgentRuntimeConfig
from heatgrid_ops.agent.contracts import (
    ChatModelRequest,
    EvidenceAssessmentRequest,
    ReportWriteRequest,
)
from heatgrid_ops.agent.diagnostics import DiagnosticModelPort
from heatgrid_ops.agent.errors import AgentDependencyError
from heatgrid_ops.agent.helpers import fallback_note, to_json
from heatgrid_ops.agent.models import (
    JsonObject,
    JsonValue,
    ModelVerificationResult,
    OpsAgentOutput,
    TokenUsage,
    TokenCall,
)
from heatgrid_ops.agent.ports import (
    ChatModelPort,
    ExternalDataPort,
    ModelVerificationPort,
    RagEvidencePort,
    ReportWriterPort,
)
from heatgrid_ops.agent.run_models import (
    ChatModelAssessmentResult,
    ExternalDataRequest,
    ExternalDataSnapshot,
    ModelVerificationRequest,
    ModelVerificationSnapshot,
    RagEvidenceRequest,
    ReportArtifactDraft,
)


@dataclass(frozen=True, slots=True)
class AgentRuntime:
    config: AgentRuntimeConfig
    rag: RagEvidencePort
    external_data: ExternalDataPort
    chat_model: ChatModelPort
    model_verification: ModelVerificationPort
    report_writer: ReportWriterPort
    diagnostic_model: DiagnosticModelPort | None = None

    async def external_context_for(
        self,
        card_id: str,
        source_input: JsonObject,
        *,
        top_k: int | None = None,
    ) -> JsonObject:
        rag = await self.rag.search(
            RagEvidenceRequest(
                card_id=card_id,
                source_input=source_input,
                top_k=top_k or self.config.rag_top_k,
            )
        )
        request = _external_data_request(source_input)
        external = (
            await self.external_data.snapshot(request)
            if request is not None
            else _unavailable_external_data()
        )
        return {
            "status": _context_status(rag.status, external.status),
            "retrieval": rag.retrieval,
            "references": rag.references,
            "site": external.site,
            "weather": external.weather,
        }

    def token_usage_for(
        self,
        source_input: JsonObject,
        evidence_context: JsonObject,
        card_id: str,
    ) -> TokenUsage:
        payload_size = len(
            to_json(
                {
                    "card_id": card_id,
                    "source_input": source_input,
                    "external_context": evidence_context,
                }
            )
        )
        return TokenUsage(evidence_payload_chars=payload_size)

    async def generate_llm_output(
        self,
        source_input: JsonObject,
        evidence_context: JsonObject,
        card_id: str,
        *,
        model_verification: ModelVerificationResult | None = None,
        evidence_assessment: EvidenceAssessment | None = None,
        revision_feedback: list[str] | None = None,
        usage: TokenUsage | None = None,
    ) -> OpsAgentOutput:
        result = await self.chat_model.generate(
            ChatModelRequest(
                card_id=card_id,
                source_input=source_input,
                evidence_context=evidence_context,
                model_verification=model_verification,
                evidence_assessment=evidence_assessment,
                revision_feedback=revision_feedback or [],
            )
        )
        if usage is not None:
            usage.calls.extend(result.calls)
        return result.output

    async def assess_evidence(
        self,
        *,
        source_input: JsonObject,
        evidence_context: JsonObject,
        model_verification: ModelVerificationResult | None,
        iteration: int,
        max_iterations: int,
        diagnostic_available: bool = False,
        force_review: bool = False,
        calls: list[TokenCall] | None = None,
    ) -> EvidenceAssessment:
        deterministic = assess_evidence(
            source_input=source_input,
            external_context=evidence_context,
            model_verification=model_verification,
            iteration=iteration,
            max_iterations=max_iterations,
            threshold=self.config.agent_evidence_threshold,
            diagnostic_available=diagnostic_available,
            force_review=force_review,
        )
        candidate = await self.chat_model.assess(
            EvidenceAssessmentRequest(
                source_input=source_input,
                evidence_context=evidence_context,
                model_verification=model_verification,
                iteration=iteration,
                max_iterations=max_iterations,
                deterministic=deterministic,
            )
        )
        if candidate is None:
            return deterministic
        if isinstance(candidate, ChatModelAssessmentResult):
            if calls is not None:
                calls.extend(candidate.calls)
            candidate = candidate.assessment
        return guard_llm_assessment(
            candidate,
            deterministic,
            iteration=iteration,
            max_iterations=max_iterations,
            model_verification=model_verification,
        )

    async def verify_models(
        self,
        request: ModelVerificationRequest,
    ) -> ModelVerificationSnapshot:
        return await self.model_verification.verify(request)

    async def write_anomaly(
        self,
        request: ReportWriteRequest,
    ) -> ReportArtifactDraft:
        return await self.report_writer.write_anomaly(request)

    async def write_daily(
        self,
        request: ReportWriteRequest,
    ) -> ReportArtifactDraft:
        return await self.report_writer.write_daily(request)

    async def stream_events(
        self,
        card_id: str,
        source_input: JsonObject,
    ) -> AsyncIterator[tuple[str, str, JsonValue | None, TokenUsage, OpsAgentOutput]]:
        evidence_context = await self.external_context_for(card_id, source_input)
        output = fallback_note(source_input, evidence_context)
        usage = self.token_usage_for(source_input, evidence_context, card_id)
        request = ChatModelRequest(
            card_id=card_id,
            source_input=source_input,
            evidence_context=evidence_context,
        )
        try:
            async for event in self.chat_model.stream(request):
                if event.token_call is not None:
                    usage.calls.append(event.token_call)
                if event.output is not None:
                    output = event.output
                yield event.kind, event.message, event.payload, usage, output
        except AgentDependencyError as exc:
            yield "fallback", str(exc), None, usage, output


async def generate_note(
    runtime: AgentRuntime,
    card_id: str,
    source_input: JsonObject,
) -> tuple[OpsAgentOutput, Literal["llm", "fallback"], TokenUsage]:
    evidence_context = await runtime.external_context_for(card_id, source_input)
    usage = runtime.token_usage_for(source_input, evidence_context, card_id)
    try:
        output = await runtime.generate_llm_output(
            source_input,
            evidence_context,
            card_id,
            usage=usage,
        )
    except AgentDependencyError:
        return fallback_note(source_input, evidence_context), "fallback", usage
    return output, "llm", usage


def _external_data_request(source_input: JsonObject) -> ExternalDataRequest | None:
    raw_context = source_input.get("raw_context")
    if not isinstance(raw_context, dict):
        return None
    window = raw_context.get("window")
    if not isinstance(window, dict):
        return None
    substation_id = window.get("substation_id")
    window_start = window.get("window_start")
    window_end = window.get("window_end")
    if not isinstance(substation_id, int):
        return None
    if not isinstance(window_start, str) or not isinstance(window_end, str):
        return None
    return ExternalDataRequest(
        substation_id=substation_id,
        window_start=window_start,
        window_end=window_end,
    )


def _unavailable_external_data() -> ExternalDataSnapshot:
    return ExternalDataSnapshot(
        status="unavailable",
        site={"status": "unavailable"},
        weather={"status": "unavailable", "provenance": "missing_window"},
    )


def _context_status(rag_status: str, external_status: str) -> str:
    if rag_status == "available" or external_status == "available":
        return "configured"
    return "configured_no_match"
