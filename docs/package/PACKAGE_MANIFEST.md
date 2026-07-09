# Repository Manifest

저장소에 포함된 실행 코드, 데이터 계약, 모델 파일, score/card, 보고 자료를 한눈에 보는 목록이다.

## 1. 실행 코드

| 경로 | 설명 |
|---|---|
| `scripts/run_3rd_model_pipeline.py` | CLI 진입점 |
| `src/third_model/pipeline.py` | `all`, `full_retrain`, 개별 step orchestration |
| `src/third_model/config.py` | 상대 경로, source 자동 탐색, 환경변수 처리 |
| `src/third_model/retrain.py` | 원천 current-best/M1 specialist 재학습 wrapper |
| `src/third_model/data_io.py` | raw inventory, canonical window import |
| `src/third_model/best_bridge.py` | current-best score/model artifact bridge |
| `src/third_model/anomaly.py` | M1 anomaly 모델 학습/score |
| `src/third_model/m1_specialist_gates.py` | M1 gate model materialize 및 병렬 score 생성 |
| `src/third_model/m1_specialist.py` | current-best와 M1 specialist hybrid priority 결합 |
| `src/third_model/operational.py` | agent card, column dictionary, action/review 생성 |
| `src/third_model/validation.py` | coverage, threshold, ablation, report 생성 |

## 2. 데이터 계약

| 경로 | 설명 |
|---|---|
| `data/interim/raw_inventory.csv` | raw 파일 inventory |
| `data/interim/raw_schema_summary.csv` | raw schema 요약 |
| `data/processed/trainable_windows.csv` | M1 canonical trainable windows, 1252 rows |
| `data/processed/feature_columns.csv` | current-best feature column 계약 |
| `data/processed/imputation_values.csv` | 재현용 imputation 값 |
| `data/processed/window_import_metadata.json` | canonical window import metadata |

## 3. 모델 파일

| 경로 | 설명 |
|---|---|
| `models/anomaly/standard_scaler.joblib` | M1 anomaly scaler |
| `models/anomaly/isolation_forest.joblib` | M1 IsolationForest |
| `models/anomaly/mahalanobis_ledoitwolf.joblib` | M1 Mahalanobis covariance |
| `models/anomaly/anomaly_metadata.json` | anomaly threshold/feature metadata |
| `models/risk/risk_model_best.joblib` | current-best risk 모델 본체 |
| `models/risk/risk_model_best_metadata.json` | current-best risk metadata |
| `models/leadtime/leadtime_model_best.joblib` | current-best leadtime 모델 본체 |
| `models/leadtime/leadtime_model_best_metadata.json` | current-best leadtime metadata |
| `models/priority/priority_engine_best_metadata.json` | current-best priority engine metadata |
| `models/m1_specialist/*.joblib` | M1 specialist fault/task/activity/pre-event gate 모델 |
| `models/m1_specialist/m1_full_gate_runtime_policy_metadata.json` | M1 gate runtime policy metadata |
| `models/model_artifacts_metadata.json` | model artifact materialize 결과 |

## 4. Score와 Agent Card

| 경로 | 설명 |
|---|---|
| `output/anomaly_scores.csv` | M1 anomaly score |
| `output/risk_scores.csv` | M1 범위 current-best risk score |
| `output/leadtime_scores.csv` | M1 범위 current-best leadtime score |
| `output/priority_scores.csv` | M1 범위 current-best priority score |
| `output/merged_model_scores.csv` | priority와 anomaly key merge |
| `output/m1_specialist_gate_scores.csv` | M1 specialist gate score |
| `output/m1_specialist_scores.csv` | M1 specialist priority와 hybrid score |
| `output/agent_priority_card.csv` | 공식 hybrid agent card, 1226 rows / 55 columns |
| `output/agent/m1_agent_priority_card.csv` | 공식 card 복사본 |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 단독 병렬 evidence card, 1252 rows / 29 columns |

## 5. Agent 계약 문서

| 경로 | 설명 |
|---|---|
| `docs/02_AGENT_OUTPUT_CONTRACT.md` | agent card 컬럼 계약 |
| `output/agent/agent_card_column_dictionary_ko.csv` | 컬럼 사전 |
| `output/agent/agent_card_column_groups_ko.csv` | 컬럼 그룹 CSV |
| `output/agent/agent_card_column_groups_ko.md` | 컬럼 그룹 설명 |
| `output/agent/agent_card_value_mapping_ko.md` | 주요 값 해석 |
| `output/agent_state_card_schema.json` | card schema |

## 6. 재학습 추적 파일

| 경로 | 설명 |
|---|---|
| `output/reports/source_retrain_metadata.json` | current-best source 재학습 명령, step, artifact 반영 결과 |
| `output/reports/m1_source_retrain_metadata.json` | M1 specialist source 재학습 명령, PreDist zip materialize, 모델 반영 결과 |
| `output/reports/retrain_logs/retrain_current_best.log` | current-best source 재학습 로그 |
| `output/reports/retrain_logs/retrain_m1_specialist.log` | M1 specialist source 재학습 로그 |

## 7. 비교/보고 자료

| 경로 | 설명 |
|---|---|
| `compare/m1_specialist_performance_comparison.ipynb` | 모델 후보 성능 비교 notebook |
| `compare/m1_threshold_weight_rationale_report.ipynb` | threshold/weight 선택 근거 notebook |
| `output/reports/final_validation_report.md` | 최종 검증 요약 |
| `output/reports/key_coverage_by_artifact.csv` | risk/leadtime/priority/card key coverage |
| `output/reports/missing_agent_windows.csv` | final card에서 빠진 26개 window |
| `output/reports/hybrid_selected_weight_comparison.csv` | 0.65/0.35, 0.72/0.28, 0.90/0.10 비교 |
| `output/reports/anomaly_if_mahalanobis_policy_grid.csv` | IF/Mahalanobis threshold grid |
| `output/reports/anomaly_criticality_threshold_sweep.csv` | criticality sweep |
| `output/reports/m1_gate_threshold_sweep.csv` | M1 gate threshold sweep |
| `output/reports/level_calibration_fpr_cap_sweep.csv` | FPR cap별 level calibration sweep |

## 8. 보존된 current-best 근거

| 경로 | 설명 |
|---|---|
| `artifacts/current_best/source_score_outputs/` | source가 없을 때 bridge에 쓰는 risk/leadtime/priority score 보존본 |
| `artifacts/current_best/model_metadata/` | risk/leadtime/priority metadata 보존본 |
| `artifacts/current_best/reports/` | current-best 성능/threshold/report 근거 |
| `artifacts/current_best/experiment_traces/` | 폐기하지 않은 비교 실험 trace |
