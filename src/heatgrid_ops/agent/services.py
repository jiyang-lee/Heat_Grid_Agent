from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
import logging
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from openai import OpenAIError
from pydantic import ValidationError

from heatgrid_ops.agent.assessment import (
    EvidenceAssessment,
    assess_evidence,
    guard_llm_assessment,
)
from heatgrid_ops.agent.external_search import (
    ExternalEvidenceSearchResult,
    OpenAIWebEvidenceProvider,
)
from heatgrid_ops.agent.helpers import (
    card_id_from_input,
    fallback_note,
    to_json,
    token_call_from_event,
    token_calls_from_messages,
    unavailable_external_context,
)
from heatgrid_ops.agent.tools import make_operational_tools
from heatgrid_rag.search import RagSearcher
from schemas import JsonValue, ModelVerificationResult, OpsAgentOutput, TokenUsage
from settings import SYSTEM_PROMPT, Settings


LOGGER = logging.getLogger(__name__)


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
        source_input: dict[str, JsonValue],
        *,
        top_k: int | None = None,
    ) -> dict[str, JsonValue]:
        try:
            return self.rag_searcher.external_context(
                card_id=card_id,
                evidence=source_input,
                top_k=top_k or self.settings.rag_top_k,
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
                    "external_context": external_context,
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
        external_candidates: list[dict[str, JsonValue]] | None = None,
        revision_feedback: list[str] | None = None,
        usage: TokenUsage | None = None,
        run_id: str = "legacy",
        stage_name: str = "report_draft",
        stage_attempt: int = 1,
        execution_profile: ExecutionProfile = "parent_evidence_agent",
        snapshot_bundle: ReportDraftSnapshotBundle | None = None,
    ) -> OpsAgentOutput:
        result = await self.chat_model.generate(
            ChatModelRequest(
                run_id=run_id,
                card_id=card_id,
                stage_name=stage_name,
                stage_attempt=stage_attempt,
                execution_profile=execution_profile,
                source_input=source_input,
                evidence_context=evidence_context,
                snapshot_bundle=snapshot_bundle,
                snapshot_bundle_hash=None
                if snapshot_bundle is None
                else snapshot_bundle.bundle_hash,
                tool_policy=_tool_policy(execution_profile),
                model_budget=_model_budget(execution_profile),
                model_verification=model_verification,
                evidence_assessment=evidence_assessment,
                revision_feedback=revision_feedback or [],
            )
        )
        enriched_context = dict(external_context)
        if model_verification is not None:
            enriched_context["model_verification"] = model_verification.model_dump(
                mode="json"
            )
        if evidence_assessment is not None:
            enriched_context["evidence_assessment"] = evidence_assessment.model_dump(
                mode="json"
            )
        if external_candidates:
            enriched_context["pending_external_evidence"] = external_candidates
        agent = create_agent(
            model,
            self.tools_for(source_input, enriched_context),
            system_prompt=SYSTEM_PROMPT,
            response_format=ToolStrategy(OpsAgentOutput),
        )
        request = f"card_id={card_id}"
        if revision_feedback:
            request += "\n이전 답변의 다음 문제를 고쳐 다시 작성하세요: " + "; ".join(
                revision_feedback
            )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": request}]}
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

    async def assess_evidence(
        self,
        *,
        source_input: dict[str, JsonValue],
        external_context: dict[str, JsonValue],
        model_verification: ModelVerificationResult | None,
        iteration: int,
        max_iterations: int,
        external_candidate_count: int,
        external_search_attempted: bool = False,
    ) -> EvidenceAssessment:
        deterministic = assess_evidence(
            source_input=source_input,
            external_context=external_context,
            model_verification=model_verification,
            iteration=iteration,
            max_iterations=max_iterations,
            threshold=self.settings.agent_evidence_threshold,
            external_search_enabled=self.settings.external_search_enabled,
            external_candidate_count=external_candidate_count,
            external_search_attempted=external_search_attempted,
        )
        key = self.settings.openai_api_key
        if key is None:
            return deterministic
        compact: dict[str, JsonValue] = {
            "iteration": iteration,
            "max_iterations": max_iterations,
            "deterministic_score": deterministic.evidence_score,
            "missing_evidence": deterministic.missing_evidence,
            "model_verification": None
            if model_verification is None
            else model_verification.model_dump(mode="json"),
            "retrieval_status": external_context.get("status"),
            "external_candidate_count": external_candidate_count,
            "external_search_attempted": external_search_attempted,
        }
        model = ChatOpenAI(
            model=self.settings.openai_model,
            api_key=key.get_secret_value(),
        ).with_structured_output(EvidenceAssessment)
        try:
            candidate = await model.ainvoke(
                [
                    (
                        "system",
                        "근거 수집 루프의 다음 행동을 선택하세요. 가능한 행동은 "
                        "expand_internal, search_external, rerun_model, request_human, "
                        "finalize입니다. 안전 관련 불확실성은 사람 검수로 보냅니다.",
                    ),
                    ("human", to_json(compact)),
                ]
            )
            candidate = EvidenceAssessment.model_validate(candidate)
            candidate = candidate.model_copy(
                update={"decision_source": "llm_guarded"}
            )
        except (OpenAIError, ValidationError, ValueError, TypeError):
            return deterministic
        return guard_llm_assessment(
            candidate,
            deterministic,
            iteration=iteration,
            max_iterations=max_iterations,
            external_search_enabled=self.settings.external_search_enabled,
            model_verification=model_verification,
        )

    async def search_external_evidence(self, query: str) -> ExternalEvidenceSearchResult:
        domains = tuple(
            item.strip()
            for item in self.settings.external_search_allowed_domains.split(",")
            if item.strip()
        )
        key = self.settings.openai_api_key
        provider = OpenAIWebEvidenceProvider(
            api_key=None if key is None else key.get_secret_value(),
            model=self.settings.external_search_model,
            max_results=self.settings.external_search_max_results,
            allowed_domains=domains,
        )
        if not self.settings.external_search_enabled:
            return ExternalEvidenceSearchResult(
                status="disabled",
                query=query,
                message="외부 검색이 비활성화되어 있습니다.",
            )
        return await provider.search(query)

    async def stream_events(
        self,
        card_id: str,
        source_input: JsonObject,
    ) -> AsyncIterator[tuple[str, str, JsonValue | None, TokenUsage, OpsAgentOutput]]:
        evidence_context = await self.external_context_for(card_id, source_input)
        output = fallback_note(source_input, evidence_context)
        usage = self.token_usage_for(source_input, evidence_context, card_id)
        request = ChatModelRequest(
            run_id="stream",
            card_id=card_id,
            stage_name="report_draft",
            stage_attempt=1,
            execution_profile="parent_evidence_agent",
            source_input=source_input,
            evidence_context=evidence_context,
            tool_policy=_tool_policy("parent_evidence_agent"),
            model_budget=_model_budget("parent_evidence_agent"),
        )
        try:
            async for event in agent.astream_events(
                {"messages": [{"role": "user", "content": f"card_id={card_id}"}]},
                version="v2",
            ):
                event_name = str(event.get("event", ""))
                run_name = str(event.get("name", ""))
                if event_name == "on_chat_model_start":
                    yield "llm", "LLM이 다음 행동을 선택하는 중", None, usage, output
                if event_name == "on_tool_start":
                    yield "tool_start", f"{run_name} 호출", None, usage, output
                if event_name == "on_tool_end":
                    yield "tool_end", f"{run_name} 결과 관측", None, usage, output
                if event_name == "on_chat_model_end":
                    usage.calls.append(token_call_from_event(event))
                if event_name == "on_chain_end" and run_name == "LangGraph":
                    data = event.get("data", {})
                    if isinstance(data, dict):
                        graph_output = data.get("output", {})
                        if isinstance(graph_output, dict):
                            result = graph_output.get("structured_response")
                            output = OpsAgentOutput.model_validate(result)
        except (
            OpenAIError,
            ValidationError,
            KeyError,
            AttributeError,
            NotImplementedError,
        ) as exc:
            LOGGER.warning(
                "Streaming LLM fallback for card_id=%s: %s: %s",
                card_id,
                type(exc).__name__,
                exc,
            )
            yield "fallback", "LLM 실행 실패, 로컬 fallback 답변 생성", None, usage, output


class MissingApiKeyError(RuntimeError):
    pass


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
            external_context,
            card_id,
            usage=usage,
        )
    except (MissingApiKeyError, OpenAIError, ValidationError) as exc:
        LOGGER.warning(
            "LLM fallback for card_id=%s: %s: %s",
            card_id,
            type(exc).__name__,
            exc,
        )
        return fallback_note(source_input, external_context), "fallback", usage
    return output, "llm", usage


def _external_data_request(source_input: JsonObject) -> ExternalDataRequest | None:
    raw_context = source_input.get("raw_context")
    if not isinstance(raw_context, dict):
        return None
    window = raw_context.get("window")
    if not isinstance(window, dict):
        return None
    substation_uid = window.get("substation_uid")
    substation_id = window.get("substation_id")
    window_start = window.get("window_start")
    window_end = window.get("window_end")
    if not isinstance(substation_uid, str) or not isinstance(substation_id, int):
        return None
    if not isinstance(window_start, str) or not isinstance(window_end, str):
        return None
    return ExternalDataRequest(
        substation_uid=substation_uid,
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


def _tool_policy(profile: ExecutionProfile) -> ToolPolicy:
    if profile in {"report_snapshot_only", "report_revision_only"}:
        return ToolPolicy(
            policy_version="agent_tool_policy.v1",
            allowed_tools=(),
            max_total_tool_calls=0,
            max_model_turns=1,
        )
    return ToolPolicy(
        policy_version="agent_tool_policy.v1",
        allowed_tools=ALL_AGENT_TOOL_NAMES,
        max_total_tool_calls=8 if profile == "parent_evidence_agent" else 2,
        max_model_turns=4 if profile == "parent_evidence_agent" else 2,
    )


def _model_budget(profile: ExecutionProfile) -> ModelCallBudget:
    report_profile = profile in {"report_snapshot_only", "report_revision_only"}
    return ModelCallBudget(
        max_input_chars=40_000 if report_profile else 80_000,
        max_output_tokens=1_000,
        max_total_tokens=8_000 if report_profile else 16_000,
        max_duration_ms=30_000,
    )
