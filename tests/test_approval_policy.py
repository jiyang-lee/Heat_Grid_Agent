from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "simulator" / "versions" / "v2_postgres_react_ops" / "backend"
sys.path.insert(0, str(BACKEND))

from heatgrid_ops.approval.policy import ApprovalPolicyContext, decide_approval
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
