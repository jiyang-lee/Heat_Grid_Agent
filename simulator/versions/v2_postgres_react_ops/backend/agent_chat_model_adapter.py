from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_openai import ChatOpenAI
from openai import OpenAIError
from pydantic import SecretStr, ValidationError

from heatgrid_ops.agent.assessment import EvidenceAssessment
from heatgrid_ops.agent.config import SYSTEM_PROMPT
from heatgrid_ops.agent.contracts import ChatModelRequest, EvidenceAssessmentRequest
from heatgrid_ops.agent.errors import AgentDependencyError, MissingApiKeyError
from heatgrid_ops.agent.helpers import to_json, token_calls_from_messages
from heatgrid_ops.agent.models import OpsAgentOutput, TokenCall
from heatgrid_ops.agent.run_models import AgentStreamEvent, ChatModelResult
from heatgrid_ops.agent.tools import make_operational_tools


@dataclass(frozen=True, slots=True)
class OpenAIChatModelAdapter:
    api_key: str | None
    model: str

    async def generate(self, request: ChatModelRequest) -> ChatModelResult:
        agent = create_agent(
            self._model(),
            make_operational_tools(request.source_input, request.evidence_context),
            system_prompt=SYSTEM_PROMPT,
            response_format=ToolStrategy(OpsAgentOutput),
        )
        prompt = f"card_id={request.card_id}"
        if request.revision_feedback:
            prompt += "\nRevise the answer for: " + "; ".join(request.revision_feedback)
        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]}
            )
            output = OpsAgentOutput.model_validate(result.get("structured_response"))
        except (OpenAIError, ValidationError, ValueError, TypeError) as exc:
            raise AgentDependencyError(service="llm", detail=str(exc)) from exc
        return ChatModelResult(
            output=output,
            calls=token_calls_from_messages(result.get("messages")),
        )

    async def assess(
        self,
        request: EvidenceAssessmentRequest,
    ) -> EvidenceAssessment | None:
        if self.api_key is None:
            return None
        compact = {
            "iteration": request.iteration,
            "max_iterations": request.max_iterations,
            "deterministic_score": request.deterministic.evidence_score,
            "missing_evidence": request.deterministic.missing_evidence,
            "model_verification": None
            if request.model_verification is None
            else request.model_verification.model_dump(mode="json"),
            "retrieval_status": request.evidence_context.get("status"),
        }
        model = self._model().with_structured_output(EvidenceAssessment)
        try:
            candidate = await model.ainvoke(
                [
                    (
                        "system",
                        "Choose one action: expand_internal, rerun_model, request_human, finalize.",
                    ),
                    ("human", to_json(compact)),
                ]
            )
            return EvidenceAssessment.model_validate(candidate).model_copy(
                update={"decision_source": "llm_guarded"}
            )
        except (OpenAIError, ValidationError, ValueError, TypeError):
            return None

    async def stream(
        self,
        request: ChatModelRequest,
    ) -> AsyncIterator[AgentStreamEvent]:
        agent = create_agent(
            self._model(),
            make_operational_tools(request.source_input, request.evidence_context),
            system_prompt=SYSTEM_PROMPT,
            response_format=ToolStrategy(OpsAgentOutput),
        )
        try:
            async for event in agent.astream_events(
                {"messages": [{"role": "user", "content": f"card_id={request.card_id}"}]},
                version="v2",
            ):
                converted = _stream_event(event)
                if converted is not None:
                    yield converted
        except (OpenAIError, ValidationError, ValueError, TypeError) as exc:
            raise AgentDependencyError(service="llm", detail=str(exc)) from exc

    def _model(self) -> ChatOpenAI:
        if self.api_key is None:
            raise MissingApiKeyError()
        return ChatOpenAI(model=self.model, api_key=SecretStr(self.api_key))


def _stream_event(event) -> AgentStreamEvent | None:
    event_name = str(event.get("event", ""))
    run_name = str(event.get("name", ""))
    if event_name == "on_chat_model_start":
        return AgentStreamEvent(kind="llm", message="LLM generation started")
    if event_name == "on_tool_start":
        return AgentStreamEvent(kind="tool_start", message=f"{run_name} started")
    if event_name == "on_tool_end":
        return AgentStreamEvent(kind="tool_end", message=f"{run_name} completed")
    if event_name == "on_chat_model_end":
        return AgentStreamEvent(
            kind="token",
            message="model usage observed",
            token_call=TokenCall(),
        )
    if event_name == "on_chain_end" and run_name == "LangGraph":
        data = event.get("data")
        if isinstance(data, dict):
            graph_output = data.get("output")
            if isinstance(graph_output, dict):
                output = OpsAgentOutput.model_validate(
                    graph_output.get("structured_response")
                )
                return AgentStreamEvent(
                    kind="final",
                    message="LLM generation completed",
                    output=output,
                )
    return None
