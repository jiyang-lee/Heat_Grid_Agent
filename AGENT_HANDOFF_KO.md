# Agent Handoff Guide

Agent/API/UI에서 읽을 파일과 컬럼 해석을 정리한 문서다.

## 필수 전달 파일

| 파일 | 역할 |
|---|---|
| `output/agent_priority_card.csv` | 공식 agent 입력 card |
| `output/agent/agent_card_value_mapping_ko.md` | 주요 값 해석 |
| `output/agent/agent_card_column_dictionary_ko.csv` | 컬럼 사전 |
| `output/agent/agent_card_column_groups_ko.md` | 컬럼 그룹 설명 |

## 선택 전달 파일

| 파일 | 설명 |
|---|---|
| `output/agent/m1_agent_priority_card.csv` | 공식 card 복사본 |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 단독 병렬 evidence card |
| `output/reports/final_validation_report.md` | 최종 검증 요약 |
| `output/reports/key_coverage_by_artifact.csv` | artifact별 key coverage |
| `output/reports/missing_agent_windows.csv` | final card에서 빠진 26개 window |
| `output/reports/hybrid_selected_weight_comparison.csv` | hybrid weight 비교 |
| `compare/m1_threshold_weight_rationale_report.ipynb` | threshold/weight 선택 근거 |

## Card 구분

| 파일 | 역할 | rows | columns |
|---|---|---:|---:|
| `output/agent_priority_card.csv` | agent/API/UI가 우선 읽는 official card | 1226 | 55 |
| `output/agent/m1_agent_priority_card.csv` | official card 복사본 | 1226 | 55 |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 specialist 단독 병렬 evidence card | 1252 | 29 |

## Agent가 우선 읽는 값

| 컬럼 | 의미 |
|---|---|
| `priority_score` | 최종 M1 hybrid priority score |
| `priority_level` | `urgent`, `high`, `medium`, `low` |
| `review_required` | 사람이 확인해야 하는 근거 충돌 또는 불확실성 여부 |
| `review_reasons` | review가 필요한 이유 |
| `trust_level` | 모델 근거 신뢰 단계 |
| `why_reason` | agent 설명용 요약 이유 |
| `recommended_action` | 권장 조치 문장 |

공식 priority:

```text
priority_score
= 0.65 * current_best_priority_score
 + 0.35 * m1_specialist_priority_score
```

## 해석 기준

| 계열 | 해석 |
|---|---|
| current-best priority | 기존 best 판단의 baseline |
| risk | supervised pre_fault 위험 신호 |
| leadtime | 우선순위 참고 긴급도, 정확한 고장 시각 단정 아님 |
| anomaly | IF/Mahalanobis 기반 정상 이탈 evidence |
| M1 specialist | M1-only 병렬 evidence, risk/leadtime 대체 아님 |
| review | 자동 결론보다 사람이 먼저 확인해야 할 사유 |

## 설명 시 같이 볼 근거

| 파일 | 설명 |
|---|---|
| `output/agent/agent_card_column_groups_ko.md` | 55개 final card 컬럼과 29개 parallel card 컬럼 분류 |
| `output/reports/row_flow_summary.csv` | 1252 -> 1226 row 흐름 |
| `output/reports/key_coverage_by_artifact.csv` | risk/leadtime/priority/card key coverage |
| `output/reports/risk_threshold_actual_values.csv` | 실제 M1 risk level cutoff |
| `output/reports/hybrid_selected_weight_comparison.csv` | hybrid weight 비교 |
| `compare/m1_threshold_weight_rationale_report.ipynb` | threshold와 weight 선택 근거 |
