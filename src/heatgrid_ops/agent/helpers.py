from __future__ import annotations

import orjson
from fastapi import HTTPException

from schemas import JsonValue, OpsAgentOutput, TokenCall


def card_id_from_input(source_input: dict[str, JsonValue]) -> str:
    priority_context = source_input["priority_context"]
    if not isinstance(priority_context, dict):
        raise HTTPException(status_code=500, detail="priority_context 형식 오류")
    card = priority_context["card"]
    if not isinstance(card, dict):
        raise HTTPException(status_code=500, detail="card 형식 오류")
    return str(card["card_id"])


def unavailable_external_context(message: str) -> dict[str, JsonValue]:
    return {
        "status": "unavailable",
        "message": message,
        "site": {"status": "unavailable"},
        "weather": {"status": "unavailable"},
        "retrieval": {"status": "unavailable", "results": []},
    }


def fallback_note(
    source_input: dict[str, JsonValue],
    external_context: dict[str, JsonValue] | None = None,
) -> OpsAgentOutput:
    priority_context = source_input["priority_context"]
    raw_context = source_input["raw_context"]
    if not isinstance(priority_context, dict) or not isinstance(raw_context, dict):
        raise HTTPException(status_code=500, detail="PostgreSQL 입력 형식 오류")
    card = priority_context["card"]
    priority = priority_context["priority"]
    explanation = priority_context["explanation"]
    window = raw_context["window"]
    if not all(isinstance(item, dict) for item in [card, priority, explanation, window]):
        raise HTTPException(status_code=500, detail="PostgreSQL 입력 세부 형식 오류")
    site = (external_context or {}).get("site")
    apartment_name = None
    if isinstance(site, dict) and site.get("status") == "mapped":
        apartment_name = site.get("apartment_name")
    location = (
        f"{apartment_name} ({window['substation_id']}번 열수급 지점)"
        if apartment_name
        else f"{window['manufacturer_id']} substation {window['substation_id']}"
    )
    return OpsAgentOutput(
        summary=(
            f"{location}에서 {priority['priority_level']} 수준의 점검 우선순위가 생성됐습니다."
        ),
        action_plan=str(
            explanation.get(
                "recommended_action",
                "우선순위 카드, 센서 근거, 위험도 산출 근거를 순서대로 확인하세요.",
            )
        ),
        caution=(
            "OPENAI_API_KEY가 없거나 LLM 호출에 실패해 로컬 fallback 답변을 사용했습니다. "
            "기상 요인과 운영 참고자료는 보조 맥락이며 고장 원인 확정 근거가 아닙니다."
        ),
    )


def token_call_from_event(event: dict[str, JsonValue]) -> TokenCall:
    data = event.get("data")
    if not isinstance(data, dict):
        return TokenCall()
    output = data.get("output")
    usage_metadata = getattr(output, "usage_metadata", {}) or {}
    if not isinstance(usage_metadata, dict):
        return TokenCall()
    input_token_details = usage_metadata.get("input_token_details", {})
    cached_input_tokens = 0
    if isinstance(input_token_details, dict):
        cached_input_tokens = int(
            input_token_details.get("cache_read")
            or input_token_details.get("cached_tokens")
            or 0
        )
    return TokenCall(
        input_tokens=int(usage_metadata.get("input_tokens", 0)),
        cached_input_tokens=cached_input_tokens,
        output_tokens=int(usage_metadata.get("output_tokens", 0)),
        total_tokens=int(usage_metadata.get("total_tokens", 0)),
    )


def to_json(payload: JsonValue) -> str:
    return orjson.dumps(payload).decode("utf-8")
