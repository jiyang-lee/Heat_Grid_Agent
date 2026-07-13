from __future__ import annotations

from heatgrid_ops.agent.contracts import EvidenceCandidateStage
from heatgrid_ops.agent.external_search import ExternalEvidenceSearchResult
from heatgrid_ops.agent.models import JsonObject
from heatgrid_ops.agent.node_context import AgentNodeContext
from heatgrid_ops.agent.nodes_audit import risk_level
from heatgrid_ops.agent.run_models import (
    AutomationPolicySnapshot,
    EvidenceCandidateRequest,
)
from heatgrid_ops.agent.state import AgentState
from heatgrid_ops.approval.policy import ApprovalPolicyContext, decide_approval


async def stage_search_hits(
    context: AgentNodeContext,
    state: AgentState,
    search: ExternalEvidenceSearchResult,
    query: str,
    policy: AutomationPolicySnapshot,
) -> tuple[list[JsonObject], list[str]]:
    candidates = list(state.get("external_candidates", []))
    candidate_ids = list(state.get("external_candidate_ids", []))
    current_risk = risk_level(state["source_input"])
    for hit in search.hits:
        approval = decide_approval(
            policy,
            ApprovalPolicyContext(
                task_type="evidence_candidate",
                risk_level=current_risk,
                confidence=hit.trust_score,
                source_trust=hit.trust_score,
            ),
        )
        stage = EvidenceCandidateStage(
            candidate=EvidenceCandidateRequest(
                run_id=state["run_id"],
                source_type="web",
                source_uri=hit.url,
                title=hit.title,
                content=hit.content,
                query=query,
                risk_level=current_risk,
                trust_score=hit.trust_score,
                metadata=hit.metadata,
                requested_by="agent-loop",
            ),
            status="auto_approved" if approval.action == "auto_approve" else "pending",
            reviewed_by="automation-policy" if approval.action == "auto_approve" else None,
            review_reason=approval.reason if approval.action == "auto_approve" else None,
        )
        candidate = await context.reviews.stage_evidence(stage)
        candidate_ids.append(candidate.candidate_id)
        candidates.append(candidate.model_dump(mode="json"))
    return candidates, candidate_ids
