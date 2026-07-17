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
    sections = _compact_sections(_mapping(source_input["sections"]))
    if requested_sections is None:
        priority = _mapping(sections.get("priority"))
        return {
            "card_id": card_id,
            "sections": sections,
            "unsupported_sections": [],
            "raw_context": {
                "window": sections.get("window"),
                "substation": sections.get("substation"),
            },
            "priority_context": {
                "card": priority.get("priority_card"),
                "priority": priority.get("priority_decision"),
                "model_outputs": sections.get("model_outputs", []),
            },
        }
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


def _compact_sections(sections: JsonObject) -> JsonObject:
    compact = dict(sections)
    compact["sensor_summaries"] = _compact_rows(
        sections.get("sensor_summaries"),
        (
            "feature_name",
            "feature_value",
            "unit",
            "meaning",
            "model_id",
            "flow_source",
            "display_rank",
        ),
    )
    compact["model_outputs"] = _compact_rows(
        sections.get("model_outputs"),
        (
            "label_name",
            "label_value",
            "score_name",
            "score_value",
            "model_family",
            "display_rank",
        ),
    )
    return compact


def _compact_rows(value: JsonValue, field_names: Sequence[str]) -> list[JsonValue]:
    if not isinstance(value, list):
        return []
    return [
        {name: row[name] for name in field_names if name in row}
        for row in value
        if isinstance(row, dict)
    ]
