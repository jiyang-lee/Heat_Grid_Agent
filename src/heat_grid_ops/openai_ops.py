from langchain.agents import create_agent
from pydantic import ValidationError
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from openai import OpenAIError

from heat_grid_ops.llm_input import get_priority_rule as build_priority_rule
from heat_grid_ops.schemas import OpsAgentLlmInput, OpsAgentOutput
from heat_grid_ops.settings import Settings

SYSTEM_PROMPT = (
    "You are a Korean district-heating operations assistant. "
    "For every request, call get_ops_input(card_id) and get_priority_rule() "
    "before writing the final answer. Return only summary, action_plan, and "
    "caution as valid structured output."
)


async def generate_ops_note(
    ops_input: OpsAgentLlmInput,
    settings: Settings,
) -> OpsAgentOutput:
    key = settings.openai_api_key
    if key is None:
        return _fallback_note(ops_input, "OPENAI_API_KEY가 없어 로컬 규칙 출력으로 대체했습니다.")

    model = ChatOpenAI(model=settings.openai_model, api_key=key.get_secret_value())
    agent = create_agent(
        model,
        _tools_for(ops_input),
        system_prompt=SYSTEM_PROMPT,
        response_format=OpsAgentOutput,
    )
    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": _prompt(ops_input)}]}
        )
        return OpsAgentOutput.model_validate(result.get("structured_response"))
    except (OpenAIError, ValidationError) as error:
        return _fallback_note(ops_input, f"OpenAI 호출 실패: {error}")


def _tools_for(ops_input: OpsAgentLlmInput) -> list[BaseTool]:
    @tool
    def get_ops_input(card_id: str) -> str:
        """Return the full ops-agent LLM input for one priority card."""
        if card_id != ops_input.handoff_context.audit_context.card_id:
            return '{"error":"card_id를 찾을 수 없습니다."}'
        return ops_input.model_dump_json()

    @tool
    def get_priority_rule() -> str:
        """Return the priority-card output rules and JSON output contract."""
        return build_priority_rule().model_dump_json()

    return [get_ops_input, get_priority_rule]


def _prompt(ops_input: OpsAgentLlmInput) -> str:
    card_id = ops_input.handoff_context.audit_context.card_id
    return (
        f"card_id={card_id}. "
        "반드시 get_ops_input(card_id)와 get_priority_rule() 도구를 모두 호출한 뒤 "
        "운영자용 summary/action_plan/caution을 생성하세요."
    )


def _fallback_note(ops_input: OpsAgentLlmInput, caution: str) -> OpsAgentOutput:
    priority = ops_input.event_context.priority_context.priority
    window = ops_input.event_context.raw_context.window
    return OpsAgentOutput(
        summary=(
            f"{window.manufacturer_id} substation {window.substation_id}의 "
            f"{priority.priority_level} priority 카드입니다. "
            f"최종 점수는 {priority.priority_score}이고 source는 "
            f"{priority.priority_source}입니다."
        ),
        action_plan=(
            ops_input.event_context.priority_context.explanation.recommended_action
            or "priority card와 window feature를 먼저 확인하세요."
        ),
        caution=caution,
    )
