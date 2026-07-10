from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from openai import OpenAIError
from pydantic import ValidationError

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
from schemas import JsonValue, OpsAgentOutput, TokenUsage
from settings import SYSTEM_PROMPT, Settings


@dataclass(frozen=True, slots=True)
class AgentRuntime:
    settings: Settings
    rag_searcher: RagSearcher

    def external_context_for(
        self,
        card_id: str,
        source_input: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        try:
            return self.rag_searcher.external_context(
                card_id=card_id,
                evidence=source_input,
                top_k=self.settings.rag_top_k,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return unavailable_external_context(str(exc))

    def tools_for(
        self,
        source_input: dict[str, JsonValue],
        external_context: dict[str, JsonValue],
    ) -> list[BaseTool]:
        return make_operational_tools(source_input, external_context)

    def token_usage_for(
        self,
        source_input: dict[str, JsonValue],
        external_context: dict[str, JsonValue],
        card_id: str,
    ) -> TokenUsage:
        payload_size = sum(
            len(item.invoke({"card_id": card_id}))
            for item in self.tools_for(source_input, external_context)
        )
        return TokenUsage(evidence_payload_chars=payload_size)

    async def generate_llm_output(
        self,
        source_input: dict[str, JsonValue],
        external_context: dict[str, JsonValue],
        card_id: str,
        usage: TokenUsage | None = None,
    ) -> OpsAgentOutput:
        key = self.settings.openai_api_key
        if key is None:
            raise MissingApiKeyError

        model = ChatOpenAI(
            model=self.settings.openai_model,
            api_key=key.get_secret_value(),
        )
        agent = create_agent(
            model,
            self.tools_for(source_input, external_context),
            system_prompt=SYSTEM_PROMPT,
            response_format=ToolStrategy(OpsAgentOutput),
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": f"card_id={card_id}"}]}
        )
        # 비스트리밍 경로에서도 실제 LLM 호출 토큰 사용량을 기록한다.
        if usage is not None:
            usage.calls.extend(token_calls_from_messages(result.get("messages")))
        return OpsAgentOutput.model_validate(result.get("structured_response"))

    async def stream_events(
        self,
        card_id: str,
        source_input: dict[str, JsonValue],
    ) -> AsyncIterator[tuple[str, str, JsonValue | None, TokenUsage, OpsAgentOutput]]:
        external_context = self.external_context_for(card_id, source_input)
        output = fallback_note(source_input, external_context)
        usage = self.token_usage_for(source_input, external_context, card_id)
        key = self.settings.openai_api_key
        if key is None:
            yield "fallback", "OPENAI_API_KEY 없음, 로컬 fallback 답변 생성", None, usage, output
            return

        model = ChatOpenAI(model=self.settings.openai_model, api_key=key.get_secret_value())
        agent = create_agent(
            model,
            self.tools_for(source_input, external_context),
            system_prompt=SYSTEM_PROMPT,
            response_format=ToolStrategy(OpsAgentOutput),
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
        except (OpenAIError, ValidationError, KeyError, AttributeError, NotImplementedError):
            yield "fallback", "LLM 실행 실패, 로컬 fallback 답변 생성", None, usage, output


class MissingApiKeyError(RuntimeError):
    pass


async def generate_note(
    runtime: AgentRuntime,
    card_id: str,
    source_input: dict[str, JsonValue],
) -> tuple[OpsAgentOutput, Literal["llm", "fallback"], TokenUsage]:
    external_context = runtime.external_context_for(card_id, source_input)
    usage = runtime.token_usage_for(source_input, external_context, card_id)
    try:
        output = await runtime.generate_llm_output(
            source_input, external_context, card_id, usage
        )
    except (MissingApiKeyError, OpenAIError, ValidationError):
        return fallback_note(source_input, external_context), "fallback", usage
    return output, "llm", usage
