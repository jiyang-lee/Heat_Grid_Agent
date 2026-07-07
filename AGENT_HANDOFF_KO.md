# Agent Handoff Guide

## 필수 전달 파일

```text
output/agent_priority_card.csv
output/agent/agent_card_value_mapping_ko.md
output/agent/agent_card_column_dictionary_ko.csv
output/agent/agent_card_column_groups_ko.md
```

## 선택 전달 파일

```text
output/agent/m1_agent_priority_card.csv
output/agent/m1_specialist_parallel_agent_card.csv
output/reports/final_validation_report.md
output/reports/key_coverage_by_artifact.csv
output/reports/missing_agent_windows.csv
output/reports/hybrid_selected_weight_comparison.csv
output/reports/anomaly_if_mahalanobis_policy_grid.csv
output/reports/m1_gate_threshold_sweep.csv
compare/m1_specialist_performance_comparison.ipynb
compare/m1_threshold_weight_rationale_report.ipynb
```

## Agent가 우선 읽는 값

```text
priority_score
priority_level
review_required
review_reasons
trust_level
why_reason
recommended_action
```

현재 `priority_score`는 최종 M1 hybrid priority다.

```text
priority_score
= 0.65 * current_best_priority_score
 + 0.35 * m1_specialist_priority_score
```

## Card 구분

| 파일 | 역할 | rows | columns |
|---|---|---:|---:|
| `output/agent_priority_card.csv` | agent/API/UI가 우선 읽는 official card | 1226 | 55 |
| `output/agent/m1_agent_priority_card.csv` | 동일한 최종 card 복사본 | 1226 | 55 |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 단독 병렬 evidence card | 1252 | 29 |

## 해석 기준

- `current_best_priority_score`는 기존 best 판단의 baseline이다.
- `risk_score`와 `risk_level_calibrated`는 current-best supervised risk 신호다.
- `predicted_lead_time_bucket`과 `leadtime_urgency_score`는 우선순위 참고 신호이며, 정확한 고장 시각 예측값으로 말하지 않는다.
- `anomaly_policy_score`는 IF ratio 0.90과 Mahalanobis ratio 1.00을 동시에 만족하는지 보는 정상 이탈 evidence다.
- `anomaly_event_label`은 anomaly가 persistence 기준까지 이어진 경우의 evidence label이다.
- `m1_specialist_*` 값은 M1 단독 specialist branch의 병렬 근거다. current-best risk/leadtime을 대체하지 않는다.
- `review_required == True`면 자동 결론보다 사람 검토가 먼저다.

## 설명 시 같이 볼 근거

| 파일 | 설명 |
|---|---|
| `output/agent/agent_card_column_groups_ko.md` | 55개 final card 컬럼과 29개 parallel card 컬럼 분류 |
| `output/reports/row_flow_summary.csv` | 1252 → 1226 row 흐름 |
| `output/reports/key_coverage_by_artifact.csv` | risk/leadtime/priority/card key coverage |
| `output/reports/risk_threshold_actual_values.csv` | 실제 risk level cutoff |
| `output/reports/hybrid_selected_weight_comparison.csv` | hybrid weight 비교 |
| `compare/m1_threshold_weight_rationale_report.ipynb` | threshold와 weight 선택 근거 |
