from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from openai import AsyncOpenAI, OpenAIError

LOGGER = logging.getLogger(__name__)

GuardrailReason = Literal["harmful_content", "profanity", "prompt_injection"]

REJECTION_MESSAGE = "부적절한 내용이 포함되어 있어 처리할 수 없습니다."

MODERATION_MODEL = "omni-moderation-latest"

FALLBACK_ASSISTANT_REPLY = (
    "요청하신 내용에 대한 답변을 생성할 수 없습니다. 질문을 다시 표현해 주세요."
)


@dataclass(frozen=True, slots=True)
class GuardrailVerdict:
    allowed: bool
    reason: GuardrailReason | None = None


_ALLOWED_VERDICT = GuardrailVerdict(allowed=True)

# Common Korean profanity/insult roots. Deliberately limited to general-purpose
# swearing/insults; no slurs targeting protected groups, politics, or religion.
_PROFANITY_ROOTS = (
    "씨발", "시발", "씨팔", "시팔", "씨바", "시바",
    "개새끼", "개새기", "개색기", "개색끼",
    "병신", "병신아", "븅신",
    "지랄", "졸라", "좆", "존나", "쓰레기같", "미친놈", "미친년",
    "새끼", "새기", "닥쳐", "닥치라", "꺼져",
    "fuck", "fuck you", "shit", "asshole", "bitch",
)

# Jailbreak / prompt-injection framings, grouped by category for maintainability.
_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        # role-spoofing
        r"system\s*:",
        r"assistant\s*:",
        r"너는\s*이제",
        r"지금부터\s*너는",
        r"지금부터\s*당신은",
        # rule-override framing
        r"규칙을\s*무시",
        r"이전\s*지시(사항)?\s*(를|을)?\s*무시",
        r"ignore\s+(all|previous|above)\s+instructions",
        r"위\s*지시(사항)?\s*(를|을)?\s*무시",
        # persona / DAN-style jailbreaks
        r"\bdan\b",
        r"역할\s*놀이|역할극",
        r"제한\s*없이\s*(답변|대답|행동)",
        r"개발자\s*모드",
        r"이제부터\s*제약\s*없이",
        # prompt / key exfiltration
        r"system\s*prompt",
        r"도구\s*호출",
        r"api\s*key",
        r"내부\s*프롬프트",
        r"프롬프트를?\s*(보여|알려|출력)",
        r"지시문을?\s*(보여|알려|출력)",
    )
)

_WHITESPACE_RE = re.compile(r"\s+")
_ZERO_WIDTH_RE = re.compile(r"[​‌‍﻿]")


def _normalize(content: str) -> str:
    normalized = unicodedata.normalize("NFKC", content)
    normalized = _ZERO_WIDTH_RE.sub("", normalized)
    normalized = normalized.casefold()
    normalized = _WHITESPACE_RE.sub(" ", normalized).strip()
    # collapse spacing used to evade word matching, e.g. "시 발" / "s y s t e m"
    return normalized


def check_pattern_guardrails(content: str) -> GuardrailVerdict:
    normalized = _normalize(content)
    collapsed = normalized.replace(" ", "")
    for root in _PROFANITY_ROOTS:
        if root in normalized or root in collapsed:
            return GuardrailVerdict(allowed=False, reason="profanity")
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(normalized) or pattern.search(collapsed):
            return GuardrailVerdict(allowed=False, reason="prompt_injection")
    return _ALLOWED_VERDICT


async def check_moderation_api(content: str, *, api_key: str | None) -> GuardrailVerdict:
    if api_key is None:
        return _ALLOWED_VERDICT
    try:
        async with AsyncOpenAI(api_key=api_key) as client:
            response = await client.moderations.create(
                model=MODERATION_MODEL,
                input=content,
            )
    except OpenAIError:
        LOGGER.warning("moderation API call failed; failing open", exc_info=True)
        return _ALLOWED_VERDICT
    except Exception:
        LOGGER.warning("moderation API call raised unexpectedly; failing open", exc_info=True)
        return _ALLOWED_VERDICT
    results = response.results
    if results and results[0].flagged:
        return GuardrailVerdict(allowed=False, reason="harmful_content")
    return _ALLOWED_VERDICT


async def check_operator_message(content: str, *, api_key: str | None) -> GuardrailVerdict:
    verdict = check_pattern_guardrails(content)
    if not verdict.allowed:
        return verdict
    return await check_moderation_api(content, api_key=api_key)


async def check_output_text(content: str, *, api_key: str | None) -> str:
    verdict = await check_moderation_api(content, api_key=api_key)
    if verdict.allowed:
        return content
    LOGGER.info("assistant reply withheld by moderation; substituting fallback")
    return FALLBACK_ASSISTANT_REPLY
