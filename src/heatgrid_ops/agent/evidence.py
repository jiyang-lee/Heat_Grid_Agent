from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from heatgrid_ops.agent.models import JsonObject, JsonValue


SUPPORTED_EVIDENCE_SECTIONS: Final = frozenset(
    {
        "priority",
        "window",
        "substation",
        "sensor_summaries",
        "model_outputs",
        "review_reasons",
        "evaluation",
    }
)


def filter_ops_evidence(
    source_input: JsonObject,
    card_id: str,
    requested_sections: Sequence[str] | None,
) -> JsonObject:
    if card_id != str(source_input["card_id"]):
        return {"error": "card_id를 찾을 수 없습니다."}
    if requested_sections is None:
        return source_input
    sections = _mapping(source_input["sections"])
    supported = [name for name in requested_sections if name in SUPPORTED_EVIDENCE_SECTIONS]
    unsupported: list[JsonValue] = [
        name for name in requested_sections if name not in SUPPORTED_EVIDENCE_SECTIONS
    ]
    return {
        "card_id": card_id,
        "sections": {name: sections[name] for name in supported},
        "unsupported_sections": unsupported,
    }


def _mapping(value: JsonValue) -> JsonObject:
    return value if isinstance(value, dict) else {}
