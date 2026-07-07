# Repository Manifest

## 실행 코드

| 경로 | 설명 |
|---|---|
| `run_3rd_model_pipeline.py` | CLI 진입점 |
| `src/third_model/pipeline.py` | `all`, `full_retrain`, 개별 step orchestration |
| `src/third_model/retrain.py` | 원천 current-best/M1 specialist 재학습 wrapper |
| `src/third_model/config.py` | 상대 경로, source 자동 탐색, 환경변수 처리 |
| `src/third_model/best_bridge.py` | current-best score/model artifact bridge |
| `src/third_model/m1_specialist_gates.py` | M1 gate model materialize 및 병렬 score 생성 |
| `src/third_model/m1_specialist.py` | current-best와 M1 specialist hybrid priority 결합 |
| `src/third_model/validation.py` | threshold, coverage, ablation, report 생성 |

## 데이터 계약

| 경로 | 설명 |
|---|---|
| `data/interim/raw_inventory.csv` | raw 파일 inventory |
| `data/interim/raw_schema_summary.csv` | raw schema 요약 |
| `data/processed/trainable_windows.csv` | M1 canonical trainable windows, 1252 rows |
| `data/processed/feature_columns.csv` | current-best feature column 계약 |
| `data/processed/imputation_values.csv` | 재현용 imputation 값 |

## 모델 파일

| 경로 | 설명 |
|---|---|
| `models/anomaly/standard_scaler.joblib` | M1 anomaly scaler |
| `models/anomaly/isolation_forest.joblib` | M1 Isolation Forest |
| `models/anomaly/mahalanobis_ledoitwolf.joblib` | M1 Mahalanobis covariance |
| `models/anomaly/anomaly_metadata.json` | anomaly threshold/feature metadata |
| `models/risk/risk_model_best.joblib` | current-best risk 모델 본체 |
| `models/risk/risk_model_best_metadata.json` | current-best risk metadata |
| `models/leadtime/leadtime_model_best.joblib` | current-best leadtime 모델 본체 |
| `models/leadtime/leadtime_model_best_metadata.json` | current-best leadtime metadata |
| `models/priority/priority_engine_best_metadata.json` | current-best priority engine metadata |
| `models/m1_specialist/*.joblib` | M1 specialist fault/task/activity/pre-event gate 모델 |
| `models/m1_specialist/m1_full_gate_runtime_policy_metadata.json` | M1 gate runtime policy metadata |
| `models/model_artifacts_metadata.json` | risk/leadtime/priority artifact materialize 결과 |

## 최종 score/card

| 경로 | 설명 |
|---|---|
| `output/risk_scores.csv` | M1 범위 current-best risk score |
| `output/leadtime_scores.csv` | M1 범위 current-best leadtime score |
| `output/priority_scores.csv` | M1 범위 current-best priority score |
| `output/anomaly_scores.csv` | M1 anomaly score |
| `output/merged_model_scores.csv` | priority와 anomaly key merge |
| `output/agent_priority_card.csv` | 최종 hybrid agent card, 1226 rows / 55 columns |
| `output/agent/m1_agent_priority_card.csv` | 최종 card 복사본 |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 단독 병렬 evidence card, 1252 rows / 29 columns |
| `output/agent/agent_card_column_groups_ko.md` | card 컬럼 분류 |

## 재학습 추적 파일

| 경로 | 설명 |
|---|---|
| `output/reports/source_retrain_metadata.json` | current-best source 재학습 명령, step, artifact 반영 결과 |
| `output/reports/m1_source_retrain_metadata.json` | M1 specialist source 재학습 명령, PreDist zip materialize, 모델 반영 결과 |
| `output/reports/retrain_logs/retrain_current_best.log` | current-best source 재학습 로그 |
| `output/reports/retrain_logs/retrain_m1_specialist.log` | M1 specialist source 재학습 로그 |

## 비교/보고 자료

| 경로 | 설명 |
|---|---|
| `compare/m1_specialist_performance_comparison.ipynb` | 모델 후보 성능 비교 notebook |
| `compare/m1_threshold_weight_rationale_report.ipynb` | threshold/weight 선택 근거 notebook |
| `output/reports/final_validation_report.md` | 최종 검증 요약 |
| `output/reports/key_coverage_by_artifact.csv` | risk/leadtime/priority/card key coverage |
| `output/reports/missing_agent_windows.csv` | agent card에서 빠진 26개 window |
| `output/reports/hybrid_selected_weight_comparison.csv` | 0.65/0.35, 0.72/0.28, 0.90/0.10 비교 |
| `output/reports/anomaly_if_mahalanobis_policy_grid.csv` | IF/Mahalanobis threshold grid |
| `output/reports/anomaly_criticality_threshold_sweep.csv` | criticality 1~10 sweep |
| `output/reports/m1_gate_threshold_sweep.csv` | M1 gate threshold sweep |
| `output/reports/level_calibration_fpr_cap_sweep.csv` | FPR cap별 level calibration sweep |

## 보존된 current-best 근거

| 경로 | 설명 |
|---|---|
| `artifacts/current_best/source_score_outputs/` | source가 없을 때 bridge에 쓰는 risk/leadtime/priority score 보존본 |
| `artifacts/current_best/model_metadata/` | risk/leadtime/priority metadata 보존본 |
| `artifacts/current_best/reports/` | current-best 성능/threshold/report 근거 |
| `artifacts/current_best/experiment_traces/` | 폐기하지 않은 비교 실험 trace |
