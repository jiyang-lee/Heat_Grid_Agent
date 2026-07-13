from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from heatgrid_ops.agent.run_models import AutomationPolicySnapshot


class ApprovalPolicyContext(BaseModel):
    task_type: str
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source_trust: float = Field(default=0.0, ge=0.0, le=1.0)
    drift_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ApprovalDecision(BaseModel):
    action: Literal["human_review", "auto_approve"]
    reason: str
    policy_eligible: bool


class ActionExecutionContext(ApprovalPolicyContext):
    explicit_user_command: bool = False
    already_executed: bool = False
    used_count: int = Field(default=0, ge=0)
    max_count: int = Field(default=1, ge=1)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    remaining_cost_usd: float | None = Field(default=None, ge=0.0)


class ActionExecutionDecision(BaseModel):
    action: Literal["execute", "reuse", "human_review", "deny"]
    reason: str
    policy_eligible: bool


def decide_approval(
    policy: AutomationPolicySnapshot,
    context: ApprovalPolicyContext,
) -> ApprovalDecision:
    eligible = _eligible(policy, context)
    if context.task_type in {"final_output", "model_promotion"}:
        return ApprovalDecision(
            action="human_review",
            reason="최종 운영 결과와 모델 승격은 항상 사람의 최종 검수를 거칩니다.",
            policy_eligible=eligible,
        )
    if context.risk_level in {"high", "critical"}:
        return ApprovalDecision(
            action="human_review",
            reason="고위험 항목은 자동 승인 범위에서 제외됩니다.",
            policy_eligible=eligible,
        )
    if policy.mode != "guarded_auto":
        return ApprovalDecision(
            action="human_review",
            reason="현재 자동화 단계에서는 사람 승인이 필요합니다.",
            policy_eligible=eligible,
        )
    if not eligible:
        return ApprovalDecision(
            action="human_review",
            reason="검수 이력, 신뢰도, 드리프트 기준을 아직 충족하지 못했습니다.",
            policy_eligible=False,
        )
    return ApprovalDecision(
        action="auto_approve",
        reason="저위험 항목이며 누적 검수 이력과 신뢰도 기준을 충족했습니다.",
        policy_eligible=True,
    )


def decide_action_execution(
    policy: AutomationPolicySnapshot,
    context: ActionExecutionContext,
) -> ActionExecutionDecision:
    if context.task_type == "external_search":
        return ActionExecutionDecision(
            action="deny",
            reason="외부 웹 검색 실행 capability는 폐기되었습니다.",
            policy_eligible=False,
        )
    if context.already_executed:
        return ActionExecutionDecision(
            action="reuse",
            reason="동일한 실행 키의 완료 결과가 있어 기존 결과를 재사용합니다.",
            policy_eligible=True,
        )
    if context.used_count >= context.max_count:
        return ActionExecutionDecision(
            action="deny",
            reason="실행당 허용된 호출 횟수를 모두 사용했습니다.",
            policy_eligible=False,
        )
    if (
        context.remaining_cost_usd is not None
        and context.estimated_cost_usd > context.remaining_cost_usd
    ):
        return ActionExecutionDecision(
            action="deny",
            reason="남은 실행 예산보다 예상 비용이 큽니다.",
            policy_eligible=False,
        )
    if context.explicit_user_command:
        return ActionExecutionDecision(
            action="execute",
            reason="운영자가 명시적으로 실행을 요청했습니다.",
            policy_eligible=True,
        )

    approval = decide_approval(policy, context)
    if approval.action == "auto_approve":
        return ActionExecutionDecision(
            action="execute",
            reason=approval.reason,
            policy_eligible=approval.policy_eligible,
        )
    return ActionExecutionDecision(
        action="human_review",
        reason=approval.reason,
        policy_eligible=approval.policy_eligible,
    )


def _eligible(
    policy: AutomationPolicySnapshot,
    context: ApprovalPolicyContext,
) -> bool:
    return bool(
        policy.reviewed_count >= policy.minimum_review_count
        and policy.approval_rate >= policy.minimum_approval_rate
        and context.confidence >= policy.minimum_confidence
        and context.source_trust >= policy.minimum_source_trust
        and context.drift_score <= policy.maximum_drift_score
    )
