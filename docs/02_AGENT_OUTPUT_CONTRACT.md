# Agent 출력 계약

최종 agent card는 `output/agent_priority_card.csv`다. 동일한 67개 컬럼이 `output/agent/m1_agent_priority_card.csv`에도 저장된다.

M1 specialist 단독 병렬 산출물은 `output/agent/m1_specialist_parallel_agent_card.csv`다. 이 파일은 29개 컬럼이며 최종 evidence gate agent contract가 아니라 M1-only evidence 확인용이다.

## 컬럼 수 요약

| file | role | rows | columns | note |
|---|---|---:|---:|---|
| `output/agent_priority_card.csv` | 최종 agent 전달 card | 1252 | 67 | agent가 우선 읽는 official card |
| `output/agent/m1_agent_priority_card.csv` | 최종 agent 전달 card 사본 | 1252 | 67 | 위 파일과 같은 컬럼 |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 specialist 단독 병렬 card | 1252 | 29 | 최종 ordering contract가 아니라 M1-only evidence |

상세 분류 파일:

```text
output/agent/agent_card_column_dictionary_ko.csv
output/agent/agent_card_column_groups_ko.csv
output/agent/agent_card_column_groups_ko.md
output/agent/agent_card_value_mapping_ko.md
```

## Column Group Summary

| 분류 | 컬럼수 | 성격 |
|---|---:|---|
| 기본 key / 설비 식별 | 5 | row identity와 화면 표시 key |
| 검증 라벨 / 보고용 ground truth | 3 | 검증/보고용 라벨. 운영 추론 입력으로 사용 금지 |
| Anomaly evidence / M1 anomaly 모델 | 9 | IF/Mahalanobis 기반 정상 이탈 evidence |
| Current-best risk 모델 | 3 | current-best supervised risk score bridge |
| Current-best leadtime / crossing evidence | 5 | leadtime bucket, urgency, crossing timing |
| Current-best priority baseline | 2 | 기존 best priority 보존값 |
| 최종 M1 Risk/pre-event gate priority contract | 19 | label-free v4 ordering과 level의 active contract 및 v3/v2 비교 필드 |
| M1 specialist 단독 evidence / hybrid input | 12 | M1-only branch. v4의 pre-event 입력과 비교용 이전 정책 입력을 제공 |
| Agent 상태 / 설명 제어 / action | 9 | review, trust, reason, action |

## Key Columns

| column | meaning |
| --- | --- |
| `manufacturer` | 제조사 또는 설비군 |
| `substation_id` | 기계실 또는 설비 ID |
| `window_start` | 분석 window 시작 시각 |
| `window_end` | 분석 window 종료 시각 |
| `configuration_type` | 설비 구성 |
| `label` | 검증용 normal/pre_fault label |
| `fault_label` | 검증용 이벤트 설명 label |
| `fault_event_id` | 검증용 이벤트 묶음 ID |

## Anomaly Columns

| column | meaning |
| --- | --- |
| `anomaly_ensemble_score` | IsolationForest와 Mahalanobis ratio를 가중합한 참고 이상 점수 |
| `anomaly_policy_score` | IF ratio 0.90과 Mahalanobis ratio 1.00 동시 충족 기준의 active 이상 점수 |
| `iforest_score_ratio` | train-normal q99 기준 IsolationForest ratio |
| `mahalanobis_score_ratio` | train-normal q99 기준 Mahalanobis ratio |
| `anomaly_consensus_count` | active threshold를 넘은 detector 개수 |
| `anomaly_criticality` | active 이상 점수 초과가 지속될 때 누적되는 counter |
| `anomaly_event_label` | active policy criticality 기준 최종 anomaly event |
| `anomaly_evidence_event_label` | agent 설명에 쓰는 active anomaly event |
| `anomaly_evidence_source` | anomaly 근거 출처 설명 |

## Risk / Leadtime Columns

| column | meaning |
| --- | --- |
| `risk_probability` | current-best risk 확률 |
| `risk_score` | priority에 들어가는 calibrated risk score |
| `risk_level_calibrated` | low/medium/high/critical 위험 단계 |
| `predicted_lead_time_bucket` | 0-24h, 1-3d, 3-7d 중 leadtime 참고 bucket |
| `leadtime_urgency_score` | leadtime이 가까울수록 커지는 긴급도 점수 |

## Priority Columns

| column | meaning |
| --- | --- |
| `current_best_priority_score` | current-best priority score |
| `current_best_priority_level` | current-best priority level |
| `m1_specialist_priority_score` | M1 specialist gate 기반 priority score |
| `m1_specialist_priority_level` | M1 specialist priority level |
| `m1_hybrid_priority_score` | current-best와 M1 specialist를 결합한 score |
| `m1_hybrid_priority_level` | hybrid priority level |
| `m1_evidence_pre_event_score` | v3 pre-event evidence 점수 |
| `m1_evidence_leadtime_score` | v3 leadtime evidence 점수 |
| `m1_risk_pre_event_priority_score` | 공식 v4 restored Risk/pre-event gate score |
| `m1_risk_pre_event_priority_level` | 공식 v4 restored Risk/pre-event gate level |
| `m1_risk_pre_event_trigger` | v4 high 조건을 만족한 Risk/pre-event 축 |
| `m1_evidence_priority_score` | 이전 v3 evidence gate score |
| `m1_evidence_priority_level` | 이전 v3 evidence gate level |
| `m1_evidence_trigger` | 이전 v3 high 조건을 만족한 evidence 축 |
| `priority_score` | 최종 agent priority score |
| `priority_level` | 최종 agent priority level |
| `priority_source` | 최종 priority 생성 방식 |
| `priority_high_label` | high 이상이면 1 |

## Specialist Evidence Columns

| column | meaning |
| --- | --- |
| `m1_specialist_fault_probability` | fault gate 확률 |
| `m1_specialist_task_probability` | task gate 확률 |
| `m1_specialist_activity_probability` | activity gate 확률 |
| `m1_specialist_pre_event_probability` | pre-event logistic 확률 |
| `m1_specialist_primary_state` | specialist가 본 주요 상태 |
| `m1_specialist_secondary_tags` | 보조 상태 tag |
| `m1_specialist_fault_group` | fault group |
| `m1_specialist_group_weight` | fault group 가중치 |
| `m1_specialist_gate_review_required` | specialist gate 기준 review 필요 여부 |
| `m1_specialist_gate_review_reasons` | specialist review 사유 |

## Operational Columns

| column | meaning |
| --- | --- |
| `shadow_priority_score` | 별도 가중치로 계산한 참고 priority score |
| `priority_policy_agreement` | 최종 priority와 shadow priority의 등급 일치 여부 |
| `operational_label` | 운영 상태 요약 |
| `primary_state` | 현재 대표 상태 |
| `review_required` | 사람이 확인해야 할 사유가 있으면 True |
| `review_reasons` | review 사유 |
| `trust_level` | 모델 근거 신뢰 단계 |
| `first_crossing_time` | 최초 alarm crossing 시점 |
| `stable_crossing_time` | 안정적으로 alarm이 유지된 시점 |
| `stable_crossing_lead_hours` | event 대비 stable crossing 선행 시간 |
| `why_reason` | agent 설명용 요약 이유 |
| `recommended_action` | 권장 조치 문장 |
