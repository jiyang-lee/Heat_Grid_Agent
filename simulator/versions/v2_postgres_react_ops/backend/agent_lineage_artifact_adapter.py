from __future__ import annotations

from dataclasses import dataclass

from heatgrid_ops.agent.lineage import canonical_json_hash
from heatgrid_ops.agent.models import JsonObject, OpsAgentOutput
from heatgrid_ops.agent.ports import ArtifactPort


@dataclass(frozen=True, slots=True)
class LineageArtifact:
    kind: str
    name: str
    uri: str
    source_output_hash: str


async def record_output_v2_artifact(
    artifacts: ArtifactPort,
    *,
    run_id: str,
    output: OpsAgentOutput,
) -> LineageArtifact:
    payload: JsonObject = {
        "summary": output.summary,
        "action_plan": output.action_plan,
        "caution": output.caution,
    }
    output_hash = canonical_json_hash(payload)
    name = "anomaly_report.json"
    uri = f"{run_id}/output_hash-{output_hash}/{name}"
    await artifacts.record(run_id, "artifact.output-v2", name, uri)
    return LineageArtifact(
        kind="artifact.output-v2",
        name=name,
        uri=uri,
        source_output_hash=output_hash,
    )
