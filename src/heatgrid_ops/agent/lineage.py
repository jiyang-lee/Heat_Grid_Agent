from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256

import orjson

from heatgrid_ops.agent.models import JsonObject, JsonValue, OpsAgentOutput


def canonical_json_hash(value: JsonObject) -> str:
    payload = orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
    return sha256(payload).hexdigest()


def source_output_hash(output: OpsAgentOutput) -> str:
    return canonical_json_hash(
        {
            "summary": output.summary,
            "action_plan": output.action_plan,
            "caution": output.caution,
        }
    )


def stage_input_hash(
    *,
    run_input_hash: str,
    upstream_output_hashes: Sequence[str],
    contract_version: str,
    policy_version: str,
    component_versions: Mapping[str, JsonValue],
    feature_flags: Mapping[str, JsonValue],
    thresholds: Mapping[str, JsonValue],
) -> str:
    sorted_upstream_hashes: list[JsonValue] = []
    for upstream_hash in sorted(upstream_output_hashes):
        sorted_upstream_hashes.append(upstream_hash)
    payload: JsonObject = {
        "run_input_hash": run_input_hash,
        "upstream_output_hashes": sorted_upstream_hashes,
        "stage_contract_version": contract_version,
        "policy_version": policy_version,
        "component_versions": dict(component_versions),
        "relevant_feature_flags": dict(feature_flags),
        "relevant_thresholds": dict(thresholds),
    }
    return canonical_json_hash(payload)
