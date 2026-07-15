from __future__ import annotations

from collections.abc import Mapping, Sequence

from heatgrid_ops.agent.lineage import stage_input_hash
from heatgrid_ops.agent.models import JsonObject, JsonValue
from heatgrid_ops.agent.v2_models import STATE_SCHEMA_VERSION, StageName
from heatgrid_ops.agent.v2_stage_contracts import stage_contract_version


def v2_stage_input_hash(
    *,
    run_input_hash: str,
    stage_name: StageName,
    upstream_output_hashes: Sequence[str],
    component_versions: Mapping[str, JsonValue],
    feature_flags: Mapping[str, JsonValue],
    thresholds: Mapping[str, JsonValue],
    attempt_parameters: Mapping[str, JsonValue] | None = None,
) -> str:
    versions: JsonObject = dict(component_versions)
    if attempt_parameters:
        versions["attempt_parameters"] = dict(attempt_parameters)
    return stage_input_hash(
        run_input_hash=run_input_hash,
        upstream_output_hashes=upstream_output_hashes,
        contract_version=stage_contract_version(stage_name),
        policy_version="agent_graph_v2.v3",
        component_versions=versions,
        feature_flags=feature_flags,
        thresholds=thresholds,
        stage_name=stage_name,
        state_schema_version=STATE_SCHEMA_VERSION,
    )
