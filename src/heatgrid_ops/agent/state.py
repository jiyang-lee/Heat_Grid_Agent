from __future__ import annotations

from typing import Literal, TypedDict

from heatgrid_ops.agent.assessment import EvidenceAssessment, OutputValidation
from heatgrid_ops.agent.models import (
    JsonValue,
    ModelVerificationResult,
    OpsAgentOutput,
    TokenUsage,
)
from heatgrid_ops.agent.run_models import AgentRunResult


class AgentState(TypedDict):
    run_id: str
    alert_id: str
    card_id: str
    approved_action_task_id: str | None
    source_input: dict[str, JsonValue]
    ops_evidence: dict[str, JsonValue]
    external_context: dict[str, JsonValue]
    external_candidates: list[dict[str, JsonValue]]
    external_candidate_ids: list[str]
    action_decisions: list[dict[str, JsonValue]]
    model_verification: ModelVerificationResult
    model_attempts: int
    active_model_artifact_uri: str
    evidence_assessment: EvidenceAssessment
    loop_iteration: int
    max_iterations: int
    output_validation: OutputValidation
    revision_count: int
    revision_feedback: list[str]
    review_task_id: str
    model_review_task_id: str
    force_review: bool
    used_tools: list[str]
    report_artifacts: list[dict[str, JsonValue]]
    report_errors: list[str]
    ops_output: OpsAgentOutput
    token_usage: TokenUsage
    agent_mode: Literal["llm", "fallback"]
    error: str
    result: AgentRunResult


class AgentStateUpdate(TypedDict, total=False):
    run_id: str
    alert_id: str
    card_id: str
    approved_action_task_id: str | None
    source_input: dict[str, JsonValue]
    ops_evidence: dict[str, JsonValue]
    external_context: dict[str, JsonValue]
    external_candidates: list[dict[str, JsonValue]]
    external_candidate_ids: list[str]
    action_decisions: list[dict[str, JsonValue]]
    model_verification: ModelVerificationResult
    model_attempts: int
    active_model_artifact_uri: str
    evidence_assessment: EvidenceAssessment
    loop_iteration: int
    max_iterations: int
    output_validation: OutputValidation
    revision_count: int
    revision_feedback: list[str]
    review_task_id: str
    model_review_task_id: str
    force_review: bool
    used_tools: list[str]
    report_artifacts: list[dict[str, JsonValue]]
    report_errors: list[str]
    ops_output: OpsAgentOutput
    token_usage: TokenUsage
    agent_mode: Literal["llm", "fallback"]
    error: str
    result: AgentRunResult


class AgentGraphInput(TypedDict):
    run_id: str
    alert_id: str
    card_id: str
    approved_action_task_id: str | None
    used_tools: list[str]
    external_candidates: list[dict[str, JsonValue]]
    external_candidate_ids: list[str]
    action_decisions: list[dict[str, JsonValue]]
    loop_iteration: int
    max_iterations: int
    model_attempts: int
    revision_count: int


class AgentGraphOutput(TypedDict):
    result: AgentRunResult
