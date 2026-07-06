from pydantic import ValidationError
from openai import AsyncOpenAI, OpenAIError

from heat_grid_ops.schemas import OpsAgentInput, OpsAgentOutput
from heat_grid_ops.settings import Settings


async def generate_ops_note(
    ops_input: OpsAgentInput,
    settings: Settings,
) -> OpsAgentOutput:
    key = settings.openai_api_key
    if key is None:
        return _fallback_note(ops_input, "OPENAI_API_KEY가 없어 로컬 규칙 출력으로 대체했습니다.")

    client = AsyncOpenAI(api_key=key.get_secret_value())
    prompt = _prompt(ops_input)
    try:
        response = await client.responses.create(
            model=settings.openai_model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You write concise Korean operations notes for district "
                        "heating priority cards. Return JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            text={"format": {"type": "json_object"}},
        )
        return OpsAgentOutput.model_validate_json(response.output_text)
    except (OpenAIError, ValidationError) as error:
        return _fallback_note(ops_input, f"OpenAI 호출 실패: {error}")


def _prompt(ops_input: OpsAgentInput) -> str:
    return (
        "다음 ops_agent_input을 읽고 JSON으로만 답하세요. "
        "필드는 summary, action_plan, caution 세 개입니다.\n\n"
        f"{ops_input.model_dump_json(indent=2)}"
    )


def _fallback_note(ops_input: OpsAgentInput, caution: str) -> OpsAgentOutput:
    priority = ops_input.priority_context.priority
    window = ops_input.raw_context.window
    return OpsAgentOutput(
        summary=(
            f"{window.manufacturer_id} substation {window.substation_id}의 "
            f"{priority.priority_level} priority 카드입니다. "
            f"최종 점수는 {priority.priority_score}이고 source는 "
            f"{priority.priority_source}입니다."
        ),
        action_plan=(
            ops_input.priority_context.explanation.recommended_action
            or "priority card와 window feature를 먼저 확인하세요."
        ),
        caution=caution,
    )
