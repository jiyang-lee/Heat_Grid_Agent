from __future__ import annotations

from collections.abc import Mapping
from typing import Final

import orjson

from heatgrid_ops.agent.lineage import canonical_json_hash
from heatgrid_ops.agent.models import JsonObject, JsonValue
from heatgrid_ops.db.migration_hook_registry import (
    MigrationConnection,
    register_data_hook,
)


INPUT_SCHEMA_VERSION: Final = "agent_input.v2"


@register_data_hook(8)
async def reconstruct_legacy_inputs(connection: MigrationConnection) -> None:
    result = await connection.execute(
        "SELECT run.run_id, run.card_id, to_jsonb(card) AS card, "
        "to_jsonb(decision) AS decision, to_jsonb(window_row) AS window_row, "
        "to_jsonb(substation) AS substation, "
        "COALESCE((SELECT jsonb_agg(to_jsonb(summary) ORDER BY summary.display_rank, "
        "summary.sensor_summary_id) FROM public.sensor_summaries summary "
        "WHERE summary.window_id = window_row.window_id), '[]'::jsonb) AS summaries, "
        "COALESCE((SELECT jsonb_agg(to_jsonb(output) ORDER BY output.display_rank, "
        "output.model_output_id) FROM public.model_outputs output "
        "WHERE output.window_id = window_row.window_id), '[]'::jsonb) AS outputs, "
        "COALESCE((SELECT jsonb_agg(to_jsonb(reason) ORDER BY reason.display_rank, "
        "reason.reason_code) FROM public.priority_card_review_reasons reason "
        "WHERE reason.card_id = card.card_id), '[]'::jsonb) AS reasons "
        "FROM public.agent_runs run "
        "JOIN public.priority_cards card ON card.card_id = run.card_id "
        "JOIN public.priority_decisions decision "
        "ON decision.priority_decision_id = card.priority_decision_id "
        "JOIN public.windows window_row ON window_row.window_id = decision.window_id "
        "LEFT JOIN public.substations substation "
        "ON substation.substation_uid = window_row.substation_uid "
        "WHERE run.input_snapshot_origin = 'legacy_v1' "
        "AND run.input_snapshot_status = 'unavailable'"
    )
    for row in await result.fetchall():
        snapshot = _source_input(row)
        input_hash = canonical_json_hash(snapshot)
        await connection.execute(
            "UPDATE public.agent_runs SET source_input_snapshot = %s::jsonb, "
            "input_schema_version = %s, input_hash = %s, "
            "input_snapshot_origin = 'legacy_reconstructed_v008', "
            "input_snapshot_status = 'available', reconstructed_at = now() "
            "WHERE run_id = %s",
            (_json(snapshot), INPUT_SCHEMA_VERSION, input_hash, row["run_id"]),
        )
        await connection.execute(
            "UPDATE public.agent_run_tasks SET input_snapshot = %s::jsonb, "
            "input_schema_version = %s, input_hash = %s, "
            "input_snapshot_origin = 'legacy_reconstructed_v008', "
            "input_snapshot_status = 'available' WHERE run_id = %s",
            (_json(snapshot), INPUT_SCHEMA_VERSION, input_hash, row["run_id"]),
        )


def _source_input(row: Mapping[str, JsonValue]) -> JsonObject:
    card = _mapping(row["card"])
    decision = _mapping(row["decision"])
    window = _mapping(row["window_row"])
    summaries = _values(row["summaries"])
    outputs = _values(row["outputs"])
    reasons = _values(row["reasons"])
    sections: JsonObject = {
        "priority": {"priority_card": card, "priority_decision": decision},
        "window": window,
        "substation": row["substation"],
        "sensor_summaries": summaries,
        "model_outputs": outputs,
        "review_reasons": reasons,
    }
    return {
        "card_id": str(card["card_id"]),
        "sections": sections,
        "unsupported_sections": [],
        "raw_context": {
            "window": window,
            "substation": row["substation"],
            "sensor_summaries": summaries,
        },
        "priority_context": {
            "card": card,
            "priority": decision,
            "model_signals": decision,
            "explanation": {
                **card,
                "review_reasons": [
                    str(_mapping(reason)["reason_code"]) for reason in reasons
                ],
            },
            "model_outputs": outputs,
        },
    }


def _mapping(value: JsonValue) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError("migration reconstruction expected a JSON object")
    return value


def _values(value: JsonValue) -> list[JsonValue]:
    if not isinstance(value, list):
        raise TypeError("migration reconstruction expected a JSON array")
    return value


def _json(value: JsonObject) -> str:
    return orjson.dumps(value, option=orjson.OPT_SORT_KEYS).decode("utf-8")
