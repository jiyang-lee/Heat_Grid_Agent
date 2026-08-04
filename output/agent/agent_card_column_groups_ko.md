# Agent Card 컬럼 분류

## 결론

- Final agent cards `output/agent_priority_card.csv` and `output/agent/m1_agent_priority_card.csv` have 1252 rows / 67 columns.
- `output/agent/m1_specialist_parallel_agent_card.csv` has 1252 rows / 29 columns and is M1-only evidence, not the final hybrid ordering contract.
- 최종 agent가 우선 읽는 active contract 컬럼은 `priority_score`, `priority_level`, `priority_source`, `priority_high_label`이다. 현재 `priority_score`는 M1 hybrid priority다.
- M1 단독 모델 계열 컬럼은 `m1_specialist_*`로 남아 있으며, 최종 priority에 35% 반영되는 근거 branch다. risk/leadtime 대체 모델로 설명하지 않는다.

## Final Hybrid Agent Card 67 columns

| 분류 | 컬럼수 | 모델/출처 | 용도 |
|---|---:|---|---|
| 기본 key / 설비 식별 | 5 | metadata / window key | 행 식별과 화면 표시 key |
| 검증 라벨 / 보고용 ground truth | 3 | 검증 라벨 전용 | 보고/평가 전용이며 운영 추론 입력으로 사용하지 않음 |
| Anomaly evidence / M1 anomaly 모델 | 9 | M1 anomaly 모델 | 정상 패턴 이탈 근거이며 단독 fault classifier가 아님 |
| Current-best risk 모델 | 3 | current-best risk 모델 / score bridge | supervised risk 중심 근거 |
| Current-best leadtime / crossing evidence | 5 | current-best leadtime 및 crossing 근거 | 긴급도와 시점 참고 근거이며 정확한 고장 시각 단정값이 아님 |
| Current-best priority baseline | 2 | current-best priority engine 기준값 | 추적성과 hybrid 비교를 위해 보존한 기준 priority |
| 최종 M1 Risk/pre-event gate priority contract | 19 | 최종 agent 계약 v4: restored Risk 0.78 OR pre-event 0.99, label-free gate | agent UI/API가 정렬과 level 판단에 우선 사용하는 v4 필드; v3와 v2는 비교용으로 보존 |
| M1 specialist 단독 evidence / hybrid input | 12 | M1 specialist 단독/병렬 근거, hybrid 입력 | M1-only 근거 branch이며 risk/leadtime 대체값이 아님 |
| Agent 상태 / 설명 제어 / action | 9 | agent 설명 및 운영 정책 계층 | 표시, review gating, 사유 문구, 권장 조치 |

### 기본 key / 설비 식별 (5)

`manufacturer`, `substation_id`, `window_start`, `window_end`, `configuration_type`

### 검증 라벨 / 보고용 ground truth (3)

`label`, `fault_label`, `fault_event_id`

### Anomaly evidence / M1 anomaly 모델 (9)

`anomaly_ensemble_score`, `anomaly_policy_score`, `iforest_score_ratio`, `mahalanobis_score_ratio`, `anomaly_consensus_count`, `anomaly_criticality`, `anomaly_event_label`, `anomaly_evidence_event_label`, `anomaly_evidence_source`

### Current-best risk 모델 (3)

`risk_probability`, `risk_score`, `risk_level_calibrated`

### Current-best leadtime / crossing evidence (5)

`predicted_lead_time_bucket`, `leadtime_urgency_score`, `first_crossing_time`, `stable_crossing_time`, `stable_crossing_lead_hours`

### Current-best priority baseline (2)

`current_best_priority_score`, `current_best_priority_level`

### 최종 M1 Risk/pre-event gate priority contract (19)

`priority_score`, `priority_level`, `priority_source`, `policy_version`, `current_best_weight`, `m1_specialist_weight`, `decision_basis`, `priority_high_label`, `m1_risk_pre_event_priority_score`, `m1_risk_pre_event_priority_level`, `m1_risk_pre_event_trigger`, `m1_evidence_pre_event_score`, `m1_evidence_leadtime_score`, `m1_evidence_priority_score`, `m1_evidence_priority_level`, `m1_evidence_trigger`, `m1_hybrid_priority_score`, `m1_hybrid_priority_level`, `m1_priority_agreement`

### M1 specialist 단독 evidence / hybrid input (12)

`m1_specialist_priority_score`, `m1_specialist_priority_level`, `m1_specialist_fault_probability`, `m1_specialist_task_probability`, `m1_specialist_activity_probability`, `m1_specialist_pre_event_probability`, `m1_specialist_primary_state`, `m1_specialist_secondary_tags`, `m1_specialist_fault_group`, `m1_specialist_group_weight`, `m1_specialist_gate_review_required`, `m1_specialist_gate_review_reasons`

### Agent 상태 / 설명 제어 / action (9)

`shadow_priority_score`, `priority_policy_agreement`, `operational_label`, `primary_state`, `review_required`, `review_reasons`, `trust_level`, `why_reason`, `recommended_action`

## M1 Specialist 병렬 Card 29개 컬럼

| 분류 | 컬럼수 | 설명 |
|---|---:|---|
| M1 parallel key / validation labels | 7 | M1 단독/병렬 근거 card 전용 |
| M1 compact window coverage | 6 | M1 단독/병렬 근거 card 전용 |
| M1 gate probability / prediction | 8 | M1 단독/병렬 근거 card 전용 |
| M1 standalone priority / review evidence | 8 | M1 단독/병렬 근거 card 전용 |

### M1 parallel key / validation labels (7)

`manufacturer`, `substation_id`, `window_start`, `window_end`, `label`, `fault_label`, `fault_event_id`

### M1 compact window coverage (6)

`m1_specialist_model_scope`, `m1_specialist_compact_window_start`, `m1_specialist_compact_window_end`, `m1_specialist_sample_count`, `m1_specialist_expected_count`, `m1_specialist_coverage_rate`

### M1 gate probability / prediction (8)

`m1_specialist_fault_probability`, `m1_specialist_task_probability`, `m1_specialist_activity_probability`, `m1_specialist_pre_event_probability`, `m1_specialist_fault_prediction`, `m1_specialist_task_prediction`, `m1_specialist_activity_prediction`, `m1_specialist_pre_event_prediction`

### M1 standalone priority / review evidence (8)

`m1_specialist_primary_state`, `m1_specialist_secondary_tags`, `m1_specialist_fault_group`, `m1_specialist_group_weight`, `m1_specialist_leadtime_urgency`, `m1_specialist_priority_score`, `m1_specialist_gate_review_required`, `m1_specialist_gate_review_reasons`

## 주의

- `label`, `fault_label`, `fault_event_id`는 검증/보고용 라벨이다. 운영 추론 입력으로 쓰면 안 된다.
- anomaly 컬럼은 정상 패턴 이탈 근거다. 단독 fault classifier로 말하지 않는다.
- current-best risk/leadtime 컬럼은 기존 best score bridge에서 온 핵심 근거다.
- M1 specialist 단독 컬럼은 M1-only 근거이며, 최종 agent ordering은 hybrid `priority_score`를 따른다.
- `m1_specialist_parallel_agent_card.csv` covers 1252 M1 windows. The final hybrid card currently has 1252 rows after joining with the current-best body.
