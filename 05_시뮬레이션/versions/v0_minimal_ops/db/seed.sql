insert into substations (manufacturer_id, substation_id, configuration_type)
values ('manufacturer 1', 31, 'SH + DHW')
on conflict (manufacturer_id, substation_id) do update
set configuration_type = excluded.configuration_type;

insert into fault_events (
    fault_event_id, manufacturer_id, substation_id, fault_label,
    estimated_lead_time_hours, lead_time_bucket
)
values (
    '45.0',
    'manufacturer 1',
    31,
    'Heat exchanger: Leakage, external',
    57.8,
    '1-3d'
)
on conflict (fault_event_id) do update
set fault_label = excluded.fault_label,
    estimated_lead_time_hours = excluded.estimated_lead_time_hours,
    lead_time_bucket = excluded.lead_time_bucket;

insert into windows (
    window_id, manufacturer_id, substation_id, window_start, window_end,
    source_file, season_bucket, label, fault_event_id
)
values (
    '00000000-0000-0000-0000-000000000001',
    'manufacturer 1',
    31,
    '2020-01-11T00:00:00Z',
    '2020-01-11T06:00:00Z',
    'substation_31.csv',
    'winter',
    'pre_fault',
    '45.0'
)
on conflict (window_id) do update
set source_file = excluded.source_file,
    season_bucket = excluded.season_bucket,
    label = excluded.label,
    fault_event_id = excluded.fault_event_id;

insert into feature_meta_map (
    feature_name, source_sensor, meaning, unit, calculation
)
values
    ('outdoor_temperature__last', 'outdoor_temperature', 'Outdoor temperature의 window 마지막 값', 'degC', 'last'),
    ('outdoor_temperature__mean', 'outdoor_temperature', 'Outdoor temperature의 window 평균', 'degC', 'mean'),
    ('p_hc1_return_temperature__last', 'p_hc1_return_temperature', 'Heat circuit 1 return temperature (primary side)의 window 마지막 값', 'degC', 'last'),
    ('p_hc1_return_temperature__mean', 'p_hc1_return_temperature', 'Heat circuit 1 return temperature (primary side)의 window 평균', 'degC', 'mean'),
    ('p_net_meter_flow__last', 'p_net_meter_flow', 'Flow의 window 마지막 값', 'l/h', 'last'),
    ('p_net_meter_flow__mean', 'p_net_meter_flow', 'Flow의 window 평균', 'l/h', 'mean'),
    ('p_net_supply_temperature__last', 'p_net_supply_temperature', 'Primary flow temperature의 window 마지막 값', 'degC', 'last'),
    ('p_net_supply_temperature__mean', 'p_net_supply_temperature', 'Primary flow temperature의 window 평균', 'degC', 'mean'),
    ('p_net_return_temperature__last', 'p_net_return_temperature', 'Primary return temperature의 window 마지막 값', 'degC', 'last'),
    ('p_net_return_temperature__mean', 'p_net_return_temperature', 'Primary return temperature의 window 평균', 'degC', 'mean'),
    ('outdoor_temperature__last_12h_mean_minus_prev_12h_mean', 'outdoor_temperature', 'Outdoor temperature의 최근 12시간 평균과 이전 12시간 평균 차이', 'degC', 'last_12h_mean_minus_prev_12h_mean'),
    ('outdoor_temperature__last_6h_mean_minus_prev_6h_mean', 'outdoor_temperature', 'Outdoor temperature의 최근 6시간 평균과 이전 6시간 평균 차이', 'degC', 'last_6h_mean_minus_prev_6h_mean'),
    ('outdoor_temperature__last_minus_first', 'outdoor_temperature', 'Outdoor temperature의 window 마지막 값과 첫 값 차이', 'degC', 'last_minus_first'),
    ('p_hc1_return_temperature__last_12h_mean_minus_prev_12h_mean', 'p_hc1_return_temperature', 'Heat circuit 1 return temperature (primary side)의 최근 12시간 평균과 이전 12시간 평균 차이', 'degC', 'last_12h_mean_minus_prev_12h_mean'),
    ('p_hc1_return_temperature__last_1d_mean_minus_prev_6d_mean', 'p_hc1_return_temperature', 'Heat circuit 1 return temperature (primary side)의 최근 1일 평균과 이전 6일 평균 차이', 'degC', 'last_1d_mean_minus_prev_6d_mean'),
    ('p_net_meter_flow__last_1d_std_minus_prev_6d_std', 'p_net_meter_flow', 'Flow의 최근 1일 표준편차와 이전 6일 표준편차 차이', 'l/h', 'last_1d_std_minus_prev_6d_std'),
    ('p_net_return_temperature__last_1d_mean_minus_prev_6d_mean', 'p_net_return_temperature', 'Primary return temperature의 최근 1일 평균과 이전 6일 평균 차이', 'degC', 'last_1d_mean_minus_prev_6d_mean'),
    ('p_return_gap__last_1d_mean_minus_prev_6d_mean', 'p_return_gap', 'Primary flow-return gap의 최근 1일 평균과 이전 6일 평균 차이', 'degC', 'last_1d_mean_minus_prev_6d_mean'),
    ('p_return_gap__last_minus_first', 'p_return_gap', 'Primary flow-return gap의 window 마지막 값과 첫 값 차이', 'degC', 'last_minus_first'),
    ('s_hc1_supply_temperature__last_1d_mean_minus_prev_6d_mean', 's_hc1_supply_temperature', 'Heat circuit 1 flow temperature (secondary)의 최근 1일 평균과 이전 6일 평균 차이', 'degC', 'last_1d_mean_minus_prev_6d_mean'),
    ('s_hc1_supply_temperature__last_1d_std_minus_prev_6d_std', 's_hc1_supply_temperature', 'Heat circuit 1 flow temperature (secondary)의 최근 1일 표준편차와 이전 6일 표준편차 차이', 'degC', 'last_1d_std_minus_prev_6d_std'),
    ('s_hc1_supply_temperature_error__last_minus_first', 's_hc1_supply_temperature_error', 'Heat circuit 1 flow temperature error의 window 마지막 값과 첫 값 차이', 'degC', 'last_minus_first'),
    ('s_hc1_supply_temperature_setpoint__last_1d_mean_minus_prev_6d_mean', 's_hc1_supply_temperature_setpoint', 'Heat circuit 1 reference flow temperature (secondary)의 최근 1일 평균과 이전 6일 평균 차이', 'degC', 'last_1d_mean_minus_prev_6d_mean')
on conflict (feature_name) do update
set source_sensor = excluded.source_sensor,
    meaning = excluded.meaning,
    unit = excluded.unit,
    calculation = excluded.calculation;

insert into window_features (
    window_id, feature_name, feature_value, feature_source, source_sensor,
    source_column, unit, calculation, display_rank
)
values
    ('00000000-0000-0000-0000-000000000001', 'outdoor_temperature__last', 4.27, 'current_best_raw_sensor', 'outdoor_temperature', 'outdoor_temperature__last', 'degC', 'last', 1),
    ('00000000-0000-0000-0000-000000000001', 'outdoor_temperature__mean', 4.471111111111111, 'current_best_raw_sensor', 'outdoor_temperature', 'outdoor_temperature__mean', 'degC', 'mean', 2),
    ('00000000-0000-0000-0000-000000000001', 'p_hc1_return_temperature__last', 34.77, 'current_best_raw_sensor', 'p_hc1_return_temperature', 'p_hc1_return_temperature__last', 'degC', 'last', 3),
    ('00000000-0000-0000-0000-000000000001', 'p_hc1_return_temperature__mean', 35.585, 'current_best_raw_sensor', 'p_hc1_return_temperature', 'p_hc1_return_temperature__mean', 'degC', 'mean', 4),
    ('00000000-0000-0000-0000-000000000001', 'p_net_meter_flow__last', 1.0, 'current_best_raw_sensor', 'p_net_meter_flow', 'p_net_meter_flow__last', 'l/h', 'last', 5),
    ('00000000-0000-0000-0000-000000000001', 'p_net_meter_flow__mean', 194.36111111111111, 'current_best_raw_sensor', 'p_net_meter_flow', 'p_net_meter_flow__mean', 'l/h', 'mean', 6),
    ('00000000-0000-0000-0000-000000000001', 'p_net_supply_temperature__last', 92.0, 'current_best_raw_sensor', 'p_net_supply_temperature', 'p_net_supply_temperature__last', 'degC', 'last', 7),
    ('00000000-0000-0000-0000-000000000001', 'p_net_supply_temperature__mean', 89.30555555555556, 'current_best_raw_sensor', 'p_net_supply_temperature', 'p_net_supply_temperature__mean', 'degC', 'mean', 8),
    ('00000000-0000-0000-0000-000000000001', 'p_net_return_temperature__last', 36.0, 'current_best_raw_sensor', 'p_net_return_temperature', 'p_net_return_temperature__last', 'degC', 'last', 9),
    ('00000000-0000-0000-0000-000000000001', 'p_net_return_temperature__mean', 34.083333333333336, 'current_best_raw_sensor', 'p_net_return_temperature', 'p_net_return_temperature__mean', 'degC', 'mean', 10),
    ('00000000-0000-0000-0000-000000000001', 'outdoor_temperature__last_12h_mean_minus_prev_12h_mean', -1.3873611111111126, 'm1_specialist_compact13', 'outdoor_temperature', 'outdoor_temperature__last_12h_mean_minus_prev_12h_mean', 'degC', 'last_12h_mean_minus_prev_12h_mean', 101),
    ('00000000-0000-0000-0000-000000000001', 'outdoor_temperature__last_6h_mean_minus_prev_6h_mean', -0.6669444444444448, 'm1_specialist_compact13', 'outdoor_temperature', 'outdoor_temperature__last_6h_mean_minus_prev_6h_mean', 'degC', 'last_6h_mean_minus_prev_6h_mean', 102),
    ('00000000-0000-0000-0000-000000000001', 'outdoor_temperature__last_minus_first', -0.21000000000000085, 'm1_specialist_compact13', 'outdoor_temperature', 'outdoor_temperature__last_minus_first', 'degC', 'last_minus_first', 103),
    ('00000000-0000-0000-0000-000000000001', 'p_hc1_return_temperature__last_12h_mean_minus_prev_12h_mean', -1.9208333333333272, 'm1_specialist_compact13', 'p_hc1_return_temperature', 'p_hc1_return_temperature__last_12h_mean_minus_prev_12h_mean', 'degC', 'last_12h_mean_minus_prev_12h_mean', 104),
    ('00000000-0000-0000-0000-000000000001', 'p_hc1_return_temperature__last_1d_mean_minus_prev_6d_mean', -2.749386574074073, 'm1_specialist_compact13', 'p_hc1_return_temperature', 'p_hc1_return_temperature__last_1d_mean_minus_prev_6d_mean', 'degC', 'last_1d_mean_minus_prev_6d_mean', 105),
    ('00000000-0000-0000-0000-000000000001', 'p_net_meter_flow__last_1d_std_minus_prev_6d_std', -5.0265147897468125, 'm1_specialist_compact13', 'p_net_meter_flow', 'p_net_meter_flow__last_1d_std_minus_prev_6d_std', 'l/h', 'last_1d_std_minus_prev_6d_std', 106),
    ('00000000-0000-0000-0000-000000000001', 'p_net_return_temperature__last_1d_mean_minus_prev_6d_mean', -3.099537037037038, 'm1_specialist_compact13', 'p_net_return_temperature', 'p_net_return_temperature__last_1d_mean_minus_prev_6d_mean', 'degC', 'last_1d_mean_minus_prev_6d_mean', 107),
    ('00000000-0000-0000-0000-000000000001', 'p_return_gap__last_1d_mean_minus_prev_6d_mean', 0.35015046296296287, 'm1_specialist_compact13', 'p_return_gap', 'p_return_gap__last_1d_mean_minus_prev_6d_mean', 'degC', 'last_1d_mean_minus_prev_6d_mean', 108),
    ('00000000-0000-0000-0000-000000000001', 'p_return_gap__last_minus_first', -3.6099999999999994, 'm1_specialist_compact13', 'p_return_gap', 'p_return_gap__last_minus_first', 'degC', 'last_minus_first', 109),
    ('00000000-0000-0000-0000-000000000001', 's_hc1_supply_temperature__last_1d_mean_minus_prev_6d_mean', 0.37098379629630074, 'm1_specialist_compact13', 's_hc1_supply_temperature', 's_hc1_supply_temperature__last_1d_mean_minus_prev_6d_mean', 'degC', 'last_1d_mean_minus_prev_6d_mean', 110),
    ('00000000-0000-0000-0000-000000000001', 's_hc1_supply_temperature__last_1d_std_minus_prev_6d_std', -0.06205405213932913, 'm1_specialist_compact13', 's_hc1_supply_temperature', 's_hc1_supply_temperature__last_1d_std_minus_prev_6d_std', 'degC', 'last_1d_std_minus_prev_6d_std', 111),
    ('00000000-0000-0000-0000-000000000001', 's_hc1_supply_temperature_error__last_minus_first', 5.009999999999991, 'm1_specialist_compact13', 's_hc1_supply_temperature_error', 's_hc1_supply_temperature_error__last_minus_first', 'degC', 'last_minus_first', 112),
    ('00000000-0000-0000-0000-000000000001', 's_hc1_supply_temperature_setpoint__last_1d_mean_minus_prev_6d_mean', 0.4045601851852041, 'm1_specialist_compact13', 's_hc1_supply_temperature_setpoint', 's_hc1_supply_temperature_setpoint__last_1d_mean_minus_prev_6d_mean', 'degC', 'last_1d_mean_minus_prev_6d_mean', 113)
on conflict (window_id, feature_name) do update
set feature_value = excluded.feature_value,
    feature_source = excluded.feature_source,
    source_sensor = excluded.source_sensor,
    source_column = excluded.source_column,
    unit = excluded.unit,
    calculation = excluded.calculation,
    display_rank = excluded.display_rank;

insert into model_runs (
    model_run_id, model_family, model_name, model_version, run_type, source_artifact
)
values
    ('30000000-0000-0000-0000-000000000001', 'current_best', 'current-best', null, 'imported_score', 'm1_specialist_handoff/agent_contract/agent_priority_card.csv'),
    ('30000000-0000-0000-0000-000000000002', 'm1_specialist', 'm1-specialist', null, 'imported_score', 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv'),
    ('30000000-0000-0000-0000-000000000003', 'priority', 'm1_hybrid_current_best_0.65_m1_specialist_0.35', null, 'policy', 'm1_specialist_handoff/agent_contract/agent_priority_card.csv')
on conflict (model_run_id) do update
set model_family = excluded.model_family,
    model_name = excluded.model_name,
    model_version = excluded.model_version,
    run_type = excluded.run_type,
    source_artifact = excluded.source_artifact;

insert into model_outputs (
    model_output_id, window_id, model_run_id, model_family,
    score_name, score_value, label_name, label_value, display_rank
)
values
    ('31000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000001', 'current_best', 'current_best_priority_score', 100.0, 'current_best_priority_level', 'urgent', 1),
    ('31000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000002', 'm1_specialist', 'm1_specialist_priority_score', 70.66635910857104, 'm1_specialist_priority_level', 'medium', 2),
    ('31000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', '30000000-0000-0000-0000-000000000003', 'priority', 'priority_score', 89.73322568799986, 'priority_level', 'urgent', 3)
on conflict (model_output_id) do update
set model_family = excluded.model_family,
    score_name = excluded.score_name,
    score_value = excluded.score_value,
    label_name = excluded.label_name,
    label_value = excluded.label_value,
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
    current_best_weight,
    m1_specialist_weight,
    decision_basis,
    m1_specialist_primary_state,
    m1_specialist_fault_group,
    policy_version
)
values (
    '20000000-0000-0000-0000-000000000001',
    '00000000-0000-0000-0000-000000000001',
    100.0,
    'urgent',
    70.66635910857104,
    'medium',
    89.73322568799986,
    'urgent',
    'm1_hybrid_current_best_0.65_m1_specialist_0.35',
    'current_only_high',
    0.65,
    0.35,
    'priority_score = 0.65 * current_best_priority_score + 0.35 * m1_specialist_priority_score',
    'fault',
    'leakage_water_loss',
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
    current_best_weight = excluded.current_best_weight,
    m1_specialist_weight = excluded.m1_specialist_weight,
    decision_basis = excluded.decision_basis,
    m1_specialist_primary_state = excluded.m1_specialist_primary_state,
    m1_specialist_fault_group = excluded.m1_specialist_fault_group,
    policy_version = excluded.policy_version;

insert into priority_cards (
    card_id,
    priority_decision_id,
    operational_label,
    primary_state,
    review_required,
    trust_level,
    first_crossing_time,
    stable_crossing_time,
    stable_crossing_lead_hours,
    why_reason,
    recommended_action,
    raw_card
)
values (
    '10000000-0000-0000-0000-000000000001',
    '20000000-0000-0000-0000-000000000001',
    'urgent',
    'pre_fault',
    true,
    'medium',
    null,
    null,
    null,
    'current-best는 urgent(100.0)이고 M1 specialist는 medium(70.66635910857104)이라 0.65/0.35 hybrid 산식으로 최종 urgent가 됐다.',
    '1-3일 리드타임 후보로 표시하고 열교환기 외부 누수 가능성과 primary return/flow 계열 센서를 우선 확인한다.',
    cast('{"source_artifact":"m1_specialist_handoff/agent_contract/agent_priority_card.csv","fault_label":"Heat exchanger: Leakage, external","fault_event_id":"45.0","predicted_lead_time_bucket":"1-3d","priority_policy_agreement":"same_tier"}' as jsonb)
)
on conflict (card_id) do update
set operational_label = excluded.operational_label,
    primary_state = excluded.primary_state,
    review_required = excluded.review_required,
    trust_level = excluded.trust_level,
    first_crossing_time = excluded.first_crossing_time,
    stable_crossing_time = excluded.stable_crossing_time,
    stable_crossing_lead_hours = excluded.stable_crossing_lead_hours,
    why_reason = excluded.why_reason,
    recommended_action = excluded.recommended_action,
    raw_card = excluded.raw_card;

insert into priority_card_review_reasons (card_id, reason_code, display_rank)
values
    ('10000000-0000-0000-0000-000000000001', 'current_only_high', 1),
    ('10000000-0000-0000-0000-000000000001', 'lead_time_1_3d', 2),
    ('10000000-0000-0000-0000-000000000001', 'fault_group_leakage_water_loss', 3)
on conflict (card_id, reason_code) do update
set display_rank = excluded.display_rank;

insert into sensor_summaries (
    sensor_summary_id, card_id, window_id, flow_source, model_id, model_version,
    source_artifact, selection_rule, feature_name, source_sensor, source_column,
    meaning, unit, calculation, feature_value, display_rank, summary_text
)
values
    ('40000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow1_anomaly_current_best', 'current-best', null, 'm1_specialist_handoff/data_contract/trainable_windows.csv', 'current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N. v0 seed N=10이며 고정값은 아니다.', 'outdoor_temperature__last', 'outdoor_temperature', 'outdoor_temperature__last', 'Outdoor temperature의 window 마지막 값', 'degC', 'last', 4.27, 1, 'Outdoor temperature last = 4.27 degC'),
    ('40000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow1_anomaly_current_best', 'current-best', null, 'm1_specialist_handoff/data_contract/trainable_windows.csv', 'current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N. v0 seed N=10이며 고정값은 아니다.', 'outdoor_temperature__mean', 'outdoor_temperature', 'outdoor_temperature__mean', 'Outdoor temperature의 window 평균', 'degC', 'mean', 4.471111111111111, 2, 'Outdoor temperature mean = 4.471111111111111 degC'),
    ('40000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow1_anomaly_current_best', 'current-best', null, 'm1_specialist_handoff/data_contract/trainable_windows.csv', 'current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N. v0 seed N=10이며 고정값은 아니다.', 'p_hc1_return_temperature__last', 'p_hc1_return_temperature', 'p_hc1_return_temperature__last', 'Heat circuit 1 return temperature (primary side)의 window 마지막 값', 'degC', 'last', 34.77, 3, 'Primary-side HC1 return temperature last = 34.77 degC'),
    ('40000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow1_anomaly_current_best', 'current-best', null, 'm1_specialist_handoff/data_contract/trainable_windows.csv', 'current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N. v0 seed N=10이며 고정값은 아니다.', 'p_hc1_return_temperature__mean', 'p_hc1_return_temperature', 'p_hc1_return_temperature__mean', 'Heat circuit 1 return temperature (primary side)의 window 평균', 'degC', 'mean', 35.585, 4, 'Primary-side HC1 return temperature mean = 35.585 degC'),
    ('40000000-0000-0000-0000-000000000005', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow1_anomaly_current_best', 'current-best', null, 'm1_specialist_handoff/data_contract/trainable_windows.csv', 'current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N. v0 seed N=10이며 고정값은 아니다.', 'p_net_meter_flow__last', 'p_net_meter_flow', 'p_net_meter_flow__last', 'Flow의 window 마지막 값', 'l/h', 'last', 1.0, 5, 'Primary network flow last = 1.0 l/h'),
    ('40000000-0000-0000-0000-000000000006', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow1_anomaly_current_best', 'current-best', null, 'm1_specialist_handoff/data_contract/trainable_windows.csv', 'current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N. v0 seed N=10이며 고정값은 아니다.', 'p_net_meter_flow__mean', 'p_net_meter_flow', 'p_net_meter_flow__mean', 'Flow의 window 평균', 'l/h', 'mean', 194.36111111111111, 6, 'Primary network flow mean = 194.36111111111111 l/h'),
    ('40000000-0000-0000-0000-000000000007', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow1_anomaly_current_best', 'current-best', null, 'm1_specialist_handoff/data_contract/trainable_windows.csv', 'current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N. v0 seed N=10이며 고정값은 아니다.', 'p_net_supply_temperature__last', 'p_net_supply_temperature', 'p_net_supply_temperature__last', 'Primary flow temperature의 window 마지막 값', 'degC', 'last', 92.0, 7, 'Primary supply temperature last = 92.0 degC'),
    ('40000000-0000-0000-0000-000000000008', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow1_anomaly_current_best', 'current-best', null, 'm1_specialist_handoff/data_contract/trainable_windows.csv', 'current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N. v0 seed N=10이며 고정값은 아니다.', 'p_net_supply_temperature__mean', 'p_net_supply_temperature', 'p_net_supply_temperature__mean', 'Primary flow temperature의 window 평균', 'degC', 'mean', 89.30555555555556, 8, 'Primary supply temperature mean = 89.30555555555556 degC'),
    ('40000000-0000-0000-0000-000000000009', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow1_anomaly_current_best', 'current-best', null, 'm1_specialist_handoff/data_contract/trainable_windows.csv', 'current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N. v0 seed N=10이며 고정값은 아니다.', 'p_net_return_temperature__last', 'p_net_return_temperature', 'p_net_return_temperature__last', 'Primary return temperature의 window 마지막 값', 'degC', 'last', 36.0, 9, 'Primary return temperature last = 36.0 degC'),
    ('40000000-0000-0000-0000-000000000010', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow1_anomaly_current_best', 'current-best', null, 'm1_specialist_handoff/data_contract/trainable_windows.csv', 'current-best 입력 feature 중 화면 확인용 raw sensor 집계값 top N. v0 seed N=10이며 고정값은 아니다.', 'p_net_return_temperature__mean', 'p_net_return_temperature', 'p_net_return_temperature__mean', 'Primary return temperature의 window 평균', 'degC', 'mean', 34.083333333333336, 10, 'Primary return temperature mean = 34.083333333333336 degC'),
    ('40000000-0000-0000-0000-000000000011', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 'outdoor_temperature__last_12h_mean_minus_prev_12h_mean', 'outdoor_temperature', 'outdoor_temperature__last_12h_mean_minus_prev_12h_mean', 'Outdoor temperature의 최근 12시간 평균과 이전 12시간 평균 차이', 'degC', 'last_12h_mean_minus_prev_12h_mean', -1.3873611111111126, 1, 'Outdoor temperature 12h mean delta = -1.3873611111111126 degC'),
    ('40000000-0000-0000-0000-000000000012', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 'outdoor_temperature__last_6h_mean_minus_prev_6h_mean', 'outdoor_temperature', 'outdoor_temperature__last_6h_mean_minus_prev_6h_mean', 'Outdoor temperature의 최근 6시간 평균과 이전 6시간 평균 차이', 'degC', 'last_6h_mean_minus_prev_6h_mean', -0.6669444444444448, 2, 'Outdoor temperature 6h mean delta = -0.6669444444444448 degC'),
    ('40000000-0000-0000-0000-000000000013', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 'outdoor_temperature__last_minus_first', 'outdoor_temperature', 'outdoor_temperature__last_minus_first', 'Outdoor temperature의 window 마지막 값과 첫 값 차이', 'degC', 'last_minus_first', -0.21000000000000085, 3, 'Outdoor temperature window delta = -0.21000000000000085 degC'),
    ('40000000-0000-0000-0000-000000000014', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 'p_hc1_return_temperature__last_12h_mean_minus_prev_12h_mean', 'p_hc1_return_temperature', 'p_hc1_return_temperature__last_12h_mean_minus_prev_12h_mean', 'Heat circuit 1 return temperature (primary side)의 최근 12시간 평균과 이전 12시간 평균 차이', 'degC', 'last_12h_mean_minus_prev_12h_mean', -1.9208333333333272, 4, 'Primary-side HC1 return temperature 12h mean delta = -1.9208333333333272 degC'),
    ('40000000-0000-0000-0000-000000000015', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 'p_hc1_return_temperature__last_1d_mean_minus_prev_6d_mean', 'p_hc1_return_temperature', 'p_hc1_return_temperature__last_1d_mean_minus_prev_6d_mean', 'Heat circuit 1 return temperature (primary side)의 최근 1일 평균과 이전 6일 평균 차이', 'degC', 'last_1d_mean_minus_prev_6d_mean', -2.749386574074073, 5, 'Primary-side HC1 return temperature 1d vs 6d mean delta = -2.749386574074073 degC'),
    ('40000000-0000-0000-0000-000000000016', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 'p_net_meter_flow__last_1d_std_minus_prev_6d_std', 'p_net_meter_flow', 'p_net_meter_flow__last_1d_std_minus_prev_6d_std', 'Flow의 최근 1일 표준편차와 이전 6일 표준편차 차이', 'l/h', 'last_1d_std_minus_prev_6d_std', -5.0265147897468125, 6, 'Primary network flow volatility delta = -5.0265147897468125 l/h'),
    ('40000000-0000-0000-0000-000000000017', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 'p_net_return_temperature__last_1d_mean_minus_prev_6d_mean', 'p_net_return_temperature', 'p_net_return_temperature__last_1d_mean_minus_prev_6d_mean', 'Primary return temperature의 최근 1일 평균과 이전 6일 평균 차이', 'degC', 'last_1d_mean_minus_prev_6d_mean', -3.099537037037038, 7, 'Primary return temperature 1d vs 6d mean delta = -3.099537037037038 degC'),
    ('40000000-0000-0000-0000-000000000018', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 'p_return_gap__last_1d_mean_minus_prev_6d_mean', 'p_return_gap', 'p_return_gap__last_1d_mean_minus_prev_6d_mean', 'Primary flow-return gap의 최근 1일 평균과 이전 6일 평균 차이', 'degC', 'last_1d_mean_minus_prev_6d_mean', 0.35015046296296287, 8, 'Primary flow-return gap 1d vs 6d mean delta = 0.35015046296296287 degC'),
    ('40000000-0000-0000-0000-000000000019', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 'p_return_gap__last_minus_first', 'p_return_gap', 'p_return_gap__last_minus_first', 'Primary flow-return gap의 window 마지막 값과 첫 값 차이', 'degC', 'last_minus_first', -3.6099999999999994, 9, 'Primary flow-return gap window delta = -3.6099999999999994 degC'),
    ('40000000-0000-0000-0000-000000000020', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 's_hc1_supply_temperature__last_1d_mean_minus_prev_6d_mean', 's_hc1_supply_temperature', 's_hc1_supply_temperature__last_1d_mean_minus_prev_6d_mean', 'Heat circuit 1 flow temperature (secondary)의 최근 1일 평균과 이전 6일 평균 차이', 'degC', 'last_1d_mean_minus_prev_6d_mean', 0.37098379629630074, 10, 'Secondary HC1 supply temperature 1d vs 6d mean delta = 0.37098379629630074 degC'),
    ('40000000-0000-0000-0000-000000000021', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 's_hc1_supply_temperature__last_1d_std_minus_prev_6d_std', 's_hc1_supply_temperature', 's_hc1_supply_temperature__last_1d_std_minus_prev_6d_std', 'Heat circuit 1 flow temperature (secondary)의 최근 1일 표준편차와 이전 6일 표준편차 차이', 'degC', 'last_1d_std_minus_prev_6d_std', -0.06205405213932913, 11, 'Secondary HC1 supply temperature volatility delta = -0.06205405213932913 degC'),
    ('40000000-0000-0000-0000-000000000022', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 's_hc1_supply_temperature_error__last_minus_first', 's_hc1_supply_temperature_error', 's_hc1_supply_temperature_error__last_minus_first', 'Heat circuit 1 flow temperature error의 window 마지막 값과 첫 값 차이', 'degC', 'last_minus_first', 5.009999999999991, 12, 'Secondary HC1 supply temperature error window delta = 5.009999999999991 degC'),
    ('40000000-0000-0000-0000-000000000023', '10000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000001', 'flow2_m1_specialist', 'm1-specialist', null, 'm1_specialist_handoff/scores/m1_specialist_compact13_features.csv', 'M1 specialist compact13 전체 13개 feature', 's_hc1_supply_temperature_setpoint__last_1d_mean_minus_prev_6d_mean', 's_hc1_supply_temperature_setpoint', 's_hc1_supply_temperature_setpoint__last_1d_mean_minus_prev_6d_mean', 'Heat circuit 1 reference flow temperature (secondary)의 최근 1일 평균과 이전 6일 평균 차이', 'degC', 'last_1d_mean_minus_prev_6d_mean', 0.4045601851852041, 13, 'Secondary HC1 supply temperature setpoint 1d vs 6d mean delta = 0.4045601851852041 degC')
on conflict (sensor_summary_id) do update
set flow_source = excluded.flow_source,
    model_id = excluded.model_id,
    model_version = excluded.model_version,
    source_artifact = excluded.source_artifact,
    selection_rule = excluded.selection_rule,
    feature_name = excluded.feature_name,
    source_sensor = excluded.source_sensor,
    source_column = excluded.source_column,
    meaning = excluded.meaning,
    unit = excluded.unit,
    calculation = excluded.calculation,
    feature_value = excluded.feature_value,
    display_rank = excluded.display_rank,
    summary_text = excluded.summary_text;
