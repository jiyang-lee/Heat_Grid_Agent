from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))

from heatgrid_ops.approval.policy import (
    ActionExecutionContext,
    ApprovalPolicyContext,
    decide_action_execution,
    decide_approval,
)
from schemas import AutomationPolicy


def policy() -> AutomationPolicy:
    return AutomationPolicy(
        mode="guarded_auto",
        auto_transition_enabled=True,
        minimum_review_count=100,
        minimum_approval_rate=0.95,
        minimum_confidence=0.9,
        minimum_source_trust=0.85,
        maximum_drift_score=0.1,
        reviewed_count=150,
        approval_rate=0.98,
        eligible_for_guarded_auto=True,
        updated_at="2026-07-10T00:00:00+00:00",
    )


def test_guarded_auto_approves_only_qualified_low_risk_intermediate_work() -> None:
    decision = decide_approval(
        policy(),
        ApprovalPolicyContext(
            task_type="evidence_candidate",
            risk_level="low",
            confidence=0.94,
            source_trust=0.92,
            drift_score=0.03,
        ),
    )
    assert decision.action == "auto_approve"


def test_final_output_and_high_risk_stay_human_reviewed() -> None:
    final_output = decide_approval(
        policy(),
        ApprovalPolicyContext(
            task_type="final_output",
            risk_level="low",
            confidence=0.99,
            source_trust=0.99,
        ),
    )
    high_risk = decide_approval(
        policy(),
        ApprovalPolicyContext(
            task_type="evidence_candidate",
            risk_level="high",
            confidence=0.99,
            source_trust=0.99,
        ),
    )
    model_promotion = decide_approval(
        policy(),
        ApprovalPolicyContext(
            task_type="model_promotion",
            risk_level="low",
            confidence=0.99,
            source_trust=0.99,
        ),
    )
    retrain = decide_approval(
        policy(),
        ApprovalPolicyContext(
            task_type="retrain_approval",
            risk_level="low",
            confidence=0.99,
            source_trust=0.99,
        ),
    )
    assert final_output.action == "human_review"
    assert high_risk.action == "human_review"
    assert model_promotion.action == "human_review"
    assert retrain.action == "auto_approve"


def test_explicit_operator_command_executes_but_duplicate_reuses_result() -> None:
    human_only = policy().model_copy(update={"mode": "human_only"})
    command = decide_action_execution(
        human_only,
        ActionExecutionContext(
            task_type="daily_report",
            risk_level="low",
            explicit_user_command=True,
        ),
    )
    duplicate = decide_action_execution(
        human_only,
        ActionExecutionContext(
            task_type="daily_report",
            risk_level="low",
            explicit_user_command=True,
            already_executed=True,
            used_count=1,
            max_count=1,
        ),
    )

    assert command.action == "execute"
    assert duplicate.action == "reuse"


def test_action_execution_enforces_call_count_and_cost_budget() -> None:
    exhausted = decide_action_execution(
        policy(),
        ActionExecutionContext(
            task_type="external_search",
            risk_level="low",
            used_count=1,
            max_count=1,
        ),
    )
    over_budget = decide_action_execution(
        policy(),
        ActionExecutionContext(
            task_type="external_search",
            risk_level="low",
            estimated_cost_usd=0.02,
            remaining_cost_usd=0.01,
        ),
    )

    assert exhausted.action == "deny"
    assert over_budget.action == "deny"


def test_guarded_auto_policy_can_execute_qualified_low_risk_action() -> None:
    decision = decide_action_execution(
        policy(),
        ActionExecutionContext(
            task_type="external_search",
            risk_level="low",
            confidence=0.94,
            source_trust=0.92,
            drift_score=0.03,
        ),
    )

    assert decision.action == "execute"
