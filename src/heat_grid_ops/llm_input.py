from typing import Final

from heat_grid_ops.schemas import (
    ActionContext,
    AuditContext,
    ControlContext,
    DecisionTrace,
    EscalationContext,
    EventContext,
    HandoffContext,
    HumanReviewSignal,
    InternalContext,
    ModelInterpretation,
    OpsAgentInput,
    OpsAgentLlmInput,
    OutputContract,
    OutputContractProperties,
    OutputFieldContract,
    PolicyContext,
    PriorityCalculationTrace,
    PriorityRuleContext,
)

OUTPUT_FIELDS: Final[tuple[str, str, str]] = ("summary", "action_plan", "caution")


def get_priority_rule() -> PriorityRuleContext:
    return PriorityRuleContext(
        policy_context=PolicyContext(
            must_do=[
                "한국어로 짧고 현장 운영자가 바로 읽을 수 있게 쓴다.",
                "입력 JSON에 있는 센서값, 우선순위 점수, 모델 신호만 근거로 사용한다.",
                "현재 상태가 확정 고장인지 모델 기반 사전 경고인지 구분해서 쓴다.",
                "current-best와 M1 specialist의 판단 차이를 주의사항에 반영한다.",
                "review_required가 true이면 운영자 확인이 필요하다고 명시한다.",
            ],
            must_not_do=[
                "입력에 없는 원인, 수리 작업, 부품 교체를 확정하지 않는다.",
                "source_artifact나 내부 필드명을 운영자에게 그대로 나열하지 않는다.",
                "priority_score 산식을 다시 길게 설명하지 않는다.",
                "로컬 파일 경로나 개인 문서 경로를 언급하지 않는다.",
            ],
        ),
        output_contract=OutputContract(
            type="object",
            required=list(OUTPUT_FIELDS),
            additionalProperties=False,
            properties=OutputContractProperties(
                summary=OutputFieldContract(
                    type="string",
                    description="카드 상황을 운영자가 한눈에 이해할 수 있는 1-2문장 요약",
                ),
                action_plan=OutputFieldContract(
                    type="string",
                    description="운영자가 우선 확인할 센서/설비/판단 순서를 2-4개 행동으로 정리",
                ),
                caution=OutputFieldContract(
                    type="string",
                    description="오탐, 데이터 품질, 모델 신뢰도, 사람 검토 필요성을 짧게 정리",
                ),
            ),
        ),
    )


def build_ops_agent_llm_input(ops_input: OpsAgentInput) -> OpsAgentLlmInput:
    priority = ops_input.priority_context.priority
    signals = ops_input.priority_context.model_signals
    explanation = ops_input.priority_context.explanation
    card = ops_input.priority_context.card
    calculation = priority.calculation
    window = ops_input.raw_context.window
    rule = get_priority_rule()

    return OpsAgentLlmInput(
        event_context=EventContext(
            raw_context=ops_input.raw_context,
            priority_context=ops_input.priority_context,
            internal_context=InternalContext(
                llm_role="district_heating_operations_assistant",
                language="ko",
                audience="현장 운영자",
                task_type="single_priority_card_ops_note",
                situation_summary=(
                    f"{window.manufacturer_id} / substation {window.substation_id} "
                    f"window에서 {card.operational_label} 등급의 "
                    f"{card.primary_state} 운영 카드가 생성됨"
                ),
                operator_goal=(
                    "운영자가 현재 상황을 이해하고 우선 확인할 센서와 설비를 "
                    "결정하게 돕는다."
                ),
            ),
            decision_trace=DecisionTrace(
                priority_score=priority.priority_score,
                priority_level=priority.priority_level,
                priority_source=priority.priority_source,
                priority_calculation=PriorityCalculationTrace(
                    expression=calculation.expression,
                    current_best_weight=calculation.current_best_weight,
                    current_best_priority_score=signals.current_best_priority_score,
                    m1_specialist_weight=calculation.m1_specialist_weight,
                    m1_specialist_priority_score=signals.m1_specialist_priority_score,
                ),
                model_interpretation=ModelInterpretation(
                    current_best_priority_level=signals.current_best_priority_level,
                    m1_specialist_priority_level=signals.m1_specialist_priority_level,
                    m1_specialist_primary_state=signals.m1_specialist_primary_state,
                    m1_specialist_fault_group=signals.m1_specialist_fault_group,
                    m1_priority_agreement=priority.m1_priority_agreement,
                ),
                human_review_signal=HumanReviewSignal(
                    review_required=explanation.review_required,
                    review_reasons=explanation.review_reasons,
                    trust_level=card.trust_level,
                ),
            ),
        ),
        control_context=ControlContext(
            policy_context=rule.policy_context,
            action_context=ActionContext(
                llm_instruction=(
                    "get_ops_input(card_id)와 get_priority_rule()을 모두 호출한 뒤 "
                    "output_contract와 정확히 맞는 JSON 객체만 반환한다."
                ),
                focus_points=[
                    "urgent 카드인 이유",
                    "1-3일 리드타임 후보로 볼 수 있는지",
                    "primary return/flow 계열 센서 확인",
                    "열교환기 외부 누수 가능성 점검",
                    "trust_level medium에 따른 검토 필요성",
                ],
                recommended_action_seed=explanation.recommended_action,
            ),
            output_contract=rule.output_contract,
        ),
        handoff_context=HandoffContext(
            escalation_context=EscalationContext(
                review_required=explanation.review_required,
                review_reasons=explanation.review_reasons,
                priority_level=priority.priority_level,
                operational_label=card.operational_label,
                primary_state=card.primary_state,
                trust_level=card.trust_level,
                suspected_fault_group=signals.m1_specialist_fault_group,
            ),
            audit_context=AuditContext(
                input_kind="llm_ops_note_request",
                card_id=card.card_id,
                priority_decision_id=priority.priority_decision_id,
                window_id=window.window_id,
                expected_output_storage="LLM_OPS_NOTES",
            ),
        ),
    )
