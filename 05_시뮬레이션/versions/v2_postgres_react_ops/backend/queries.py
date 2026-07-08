from sqlalchemy import text

CURRENT_BEST_FLOW = "flow1_anomaly_current_best"
M1_SPECIALIST_FLOW = "flow2_m1_specialist"
PRIORITY_CALCULATION_EXPRESSION = (
    "priority_score = current_best_weight * current_best_priority_score + "
    "m1_specialist_weight * m1_specialist_priority_score"
)


def card_query():
    return text(
        "select "
        "pc.card_id, pc.operational_label, pc.primary_state, pc.review_required, "
        "pc.trust_level, pc.why_reason, pc.recommended_action, pc.raw_card, "
        "pd.priority_decision_id, pd.priority_score, pd.priority_level, "
        "pd.priority_source, pd.m1_priority_agreement, "
        "pd.current_best_priority_score, pd.current_best_priority_level, "
        "pd.m1_specialist_priority_score, pd.m1_specialist_priority_level, "
        "pd.current_best_weight, pd.m1_specialist_weight, "
        "pd.m1_specialist_primary_state, pd.m1_specialist_fault_group, "
        "w.window_id, w.manufacturer_id, w.substation_id, "
        "w.window_start, w.window_end, s.configuration_type "
        "from priority_cards pc "
        "join priority_decisions pd on pd.priority_decision_id = pc.priority_decision_id "
        "join windows w on w.window_id = pd.window_id "
        "left join substations s "
        "on s.manufacturer_id = w.manufacturer_id "
        "and s.substation_id = w.substation_id "
        "where pc.card_id = :card_id"
    )


def sensor_summary_query():
    return text(
        "select model_id, model_version, source_artifact, selection_rule, "
        "feature_name, source_sensor, source_column, meaning, unit, calculation, "
        "feature_value, summary_text, display_rank "
        "from sensor_summaries "
        "where card_id = :card_id and flow_source = :flow_source "
        "order by display_rank, feature_name"
    )
