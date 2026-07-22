# Handoff File Index

저장소를 받은 사람이 어떤 파일을 어떤 순서로 봐야 하는지 정리한 색인이다.

## 1. 먼저 읽을 문서

| 순서 | 파일 | 역할 |
|---:|---|---|
| 1 | `README.md` | 전체 개요와 quick start |
| 2 | `docs/README.md` | 문서 지도 |
| 3 | `docs/handoff/HANDOFF.md` | 짧은 인계 요약 |
| 4 | `docs/package/PACKAGE_README_KO.md` | 저장소 사용 안내 |
| 5 | `docs/handoff/M1_SPECIALIST_HANDOFF_KO.md` | M1 specialist 인계 |
| 6 | `docs/model/MODEL_INVENTORY_KO.md` | 모델 구성과 재학습 책임 |
| 7 | `docs/package/PACKAGE_MANIFEST.md` | 포함 파일 목록 |
| 8 | `docs/05_RUNBOOK.md` | 실행/검증 명령 |
| 9 | `docs/00_SOURCE_TRACE.md` | source 탐색과 파일 출처 |

## 2. 최종 agent card

| 파일 | 역할 | rows | columns |
|---|---|---:|---:|
| `output/agent_priority_card.csv` | 공식 Risk/pre-event gate v4 agent card | 1252 | 67 |
| `output/agent/m1_agent_priority_card.csv` | 공식 Risk/pre-event gate v4 agent card 복사본 | 1252 | 67 |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 specialist 단독 병렬 evidence card | 1252 | 29 |

컬럼 분류:

```text
output/agent/agent_card_column_dictionary_ko.csv
output/agent/agent_card_column_groups_ko.csv
output/agent/agent_card_column_groups_ko.md
output/agent/agent_card_value_mapping_ko.md
```

## 3. 모델 파일

| 폴더 | 내용 |
|---|---|
| `models/anomaly/` | M1 anomaly 모델 |
| `models/risk/` | current-best risk 모델과 metadata |
| `models/leadtime/` | current-best leadtime 모델과 metadata |
| `models/priority/` | current-best priority engine metadata |
| `models/m1_specialist/` | M1 specialist gate joblib 4개와 runtime metadata |

## 4. Score와 중간 산출물

```text
output/anomaly_scores.csv
output/risk_scores.csv
output/leadtime_scores.csv
output/priority_scores.csv
output/merged_model_scores.csv
output/m1_specialist_gate_scores.csv
output/m1_specialist_scores.csv
```

## 5. 재생성·명시적 재학습 추적

`full_retrain`을 실행한 경우 아래 파일에 검증 artifact 재사용 또는 명시적 재학습 mode가 기록된다.

```text
output/reports/source_retrain_metadata.json
output/reports/m1_source_retrain_metadata.json
output/reports/retrain_logs/retrain_current_best.log
output/reports/retrain_logs/retrain_m1_specialist.log
```

## 6. 보고/발표용 근거

| 파일 | 설명 |
|---|---|
| `compare/m1_specialist_performance_comparison.ipynb` | 후보 모델 성능 비교 |
| `compare/m1_threshold_weight_rationale_report.ipynb` | threshold/weight 선택 근거 |
| `docs/08_MODEL_REPORT_DEFENSE_AUDIT.md` | 보고서 방어 체크리스트 |
| `output/reports/final_validation_report.md` | 최종 검증 요약 |
| `output/reports/key_coverage_by_artifact.csv` | artifact별 key coverage |
| `output/reports/missing_agent_windows.csv` | final card에서 빠진 26개 window |
| `output/reports/hybrid_selected_weight_comparison.csv` | hybrid weight 비교 |
| `output/reports/m1_gate_threshold_sweep.csv` | M1 gate threshold 비교 |
| `output/reports/anomaly_if_mahalanobis_policy_grid.csv` | IF/Mahalanobis threshold grid |

## 7. Coverage 설명

M1 canonical window는 1252개다. 보존된 상위 current-best artifact의 manufacturer 1 score는 1226개였지만, 현재 패키지의 risk/leadtime/priority/M1 score와 최종 evidence gate card는 1252개 key를 모두 보존한다. `row_reconciliation.csv`와 `key_coverage_by_artifact.csv`에서 현재 누락이 0개인지 확인한다.

확인 파일:

```text
output/reports/row_flow_summary.csv
output/reports/key_coverage_by_artifact.csv
output/reports/missing_agent_windows.csv
```
