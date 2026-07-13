from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from heatgrid_ops.agent.models import ModelVerificationResult


PolicyAction = Literal[
    "rerun_model",
    "expand_internal",
    "diagnostic_worker",
    "request_human",
    "finalize",
]
PolicyHandler = Callable[["DecisionContext"], bool]


@dataclass(frozen=True, slots=True)
class DecisionContext:
    model_verification: ModelVerificationResult | None
    rag_chunk_count: int
    review_required: bool
    evidence_score: float
    evidence_threshold: float
    iteration: int
    max_iterations: int
    diagnostic_available: bool = False

    @property
    def model_disagrees(self) -> bool:
        return bool(
            self.model_verification is not None
            and self.model_verification.agreement is False
        )


@dataclass(frozen=True, slots=True)
class DecisionRule:
    name: str
    action: PolicyAction
    handler: PolicyHandler


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    rules: tuple[DecisionRule, ...]

    @property
    def priority(self) -> tuple[PolicyAction, ...]:
        return tuple(rule.action for rule in self.rules)

    def decide(self, context: DecisionContext) -> PolicyAction:
        for rule in self.rules:
            if rule.handler(context):
                return rule.action
        raise RuntimeError("decision policy has no terminal rule")


def default_decision_policy() -> DecisionPolicy:
    return DecisionPolicy(
        rules=(
            DecisionRule("model_revalidation", "rerun_model", _needs_model_rerun),
            DecisionRule("internal_rag", "expand_internal", _needs_internal_rag),
            DecisionRule(
                "diagnostic_worker",
                "diagnostic_worker",
                _needs_diagnostic_worker,
            ),
            DecisionRule("human_review", "request_human", _needs_human_review),
            DecisionRule("complete", "finalize", _always),
        )
    )


def _needs_model_rerun(context: DecisionContext) -> bool:
    verification = context.model_verification
    return bool(
        context.model_disagrees
        and verification is not None
        and verification.attempt < 2
    )


def _needs_internal_rag(context: DecisionContext) -> bool:
    return bool(
        context.rag_chunk_count < 2
        and context.iteration == 1
        and context.iteration < context.max_iterations
    )


def _needs_diagnostic_worker(context: DecisionContext) -> bool:
    return bool(
        context.diagnostic_available
        and (context.review_required or context.model_disagrees)
    )


def _needs_human_review(context: DecisionContext) -> bool:
    return bool(
        context.review_required
        or context.model_disagrees
        or context.evidence_score < context.evidence_threshold
    )


def _always(_: DecisionContext) -> bool:
    return True
