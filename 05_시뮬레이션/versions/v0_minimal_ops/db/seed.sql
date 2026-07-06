insert into substations (manufacturer_id, substation_id, configuration_type)
values ('manufacturer 1', 31, 'SH + DHW')
on conflict (manufacturer_id, substation_id) do update
set configuration_type = excluded.configuration_type;

insert into windows (
    window_id, manufacturer_id, substation_id, window_start, window_end
)
values (
    '00000000-0000-0000-0000-000000000001',
    'manufacturer 1',
    31,
    '2020-01-11T00:00:00Z',
    '2020-01-11T06:00:00Z'
)
on conflict (window_id) do nothing;

insert into window_features (window_id, feature_name, feature_value, display_rank)
values
    ('00000000-0000-0000-0000-000000000001', 'missing_rate', 0.02, 1),
    ('00000000-0000-0000-0000-000000000001', 'p_return_gap__last_minus_first', 4.2, 2)
on conflict (window_id, feature_name) do update
set feature_value = excluded.feature_value,
    display_rank = excluded.display_rank;

insert into priority_decisions (
    priority_decision_id,
    window_id,
    current_best_priority_score,
    current_best_priority_level,
    m1_specialist_priority_score,
    m1_specialist_priority_level,
    priority_score,
    priority_level,
    priority_source,
    m1_priority_agreement,
    policy_version
)
values (
    '20000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    82.1,
    'high',
    91.8,
    'urgent',
    87.4,
    'urgent',
    'hybrid',
    'agree',
    'v0_minimal_ops'
)
on conflict (priority_decision_id) do update
set current_best_priority_score = excluded.current_best_priority_score,
    current_best_priority_level = excluded.current_best_priority_level,
    m1_specialist_priority_score = excluded.m1_specialist_priority_score,
    m1_specialist_priority_level = excluded.m1_specialist_priority_level,
    priority_score = excluded.priority_score,
    priority_level = excluded.priority_level,
    priority_source = excluded.priority_source,
    m1_priority_agreement = excluded.m1_priority_agreement,
    policy_version = excluded.policy_version;

insert into priority_cards (
    card_id,
    priority_decision_id,
    operational_label,
    primary_state,
    review_required,
    trust_level,
    why_reason,
    recommended_action
)
values (
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    'urgent',
    'pre_fault',
    true,
    'medium',
    'M1 specialist and current-best both indicate elevated priority.',
    'Review the substation operation and inspect return temperature behavior.'
)
on conflict (card_id) do update
set operational_label = excluded.operational_label,
    primary_state = excluded.primary_state,
    review_required = excluded.review_required,
    trust_level = excluded.trust_level,
    why_reason = excluded.why_reason,
    recommended_action = excluded.recommended_action;
