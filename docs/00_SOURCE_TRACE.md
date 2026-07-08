# Source Trace

## source 탐색 원칙

저장소 코드는 외부 절대경로를 고정하지 않는다. 환경변수가 있으면 우선 사용하고, 없으면 저장소와 같은 상위 폴더의 source 프로젝트를 자동 탐색한다.

| source | 환경변수 | 기본 탐색 |
|---|---|---|
| current-best | `THIRD_MODEL_SOURCE_BEST_ROOT` | `../HeatGrid_Agent/best` |
| current-best Python | `THIRD_MODEL_CURRENT_BEST_PYTHON` | `../HeatGrid_Agent/.venv/Scripts/python.exe`, 없으면 현재 uv Python |
| M1 specialist | `THIRD_MODEL_3RD_PROJECT_ROOT` | `../3rd_project_for_ML-main/3rd_project_for_ML-main` |
| M1 specialist Python | `THIRD_MODEL_M1_SPECIALIST_PYTHON` | 현재 uv Python |
| PreDist zip | `THIRD_MODEL_PREDIST_ZIP_PATH` | `../HeatGrid_Agent/data/_downloads/predist_dataset.zip` |

## current-best source에서 가져오는 것

| 항목 | 저장소 위치 | 설명 |
|---|---|---|
| canonical windows | `data/processed/trainable_windows.csv` | M1 row만 필터링한 모델 입력 |
| feature contract | `data/processed/feature_columns.csv` | current-best feature column 목록 |
| imputation contract | `data/processed/imputation_values.csv` | 결측 대체값 |
| risk score | `output/risk_scores.csv` | M1 scope risk score |
| leadtime score | `output/leadtime_scores.csv` | M1 scope leadtime score |
| priority score | `output/priority_scores.csv` | M1 scope current-best priority |
| risk model | `models/risk/risk_model_best.joblib` | 재학습/traceability용 모델 본체 |
| leadtime model | `models/leadtime/leadtime_model_best.joblib` | 재학습/traceability용 모델 본체 |
| priority metadata | `models/priority/priority_engine_best_metadata.json` | priority policy metadata |

## M1 specialist source에서 가져오는 것

| 항목 | 저장소 위치 |
|---|---|
| fault gate model | `models/m1_specialist/m1_fault_gate_rf_depth3.joblib` |
| task gate model | `models/m1_specialist/m1_task_gate_rf_depth3.joblib` |
| activity gate model | `models/m1_specialist/m1_activity_gate_rf_depth3.joblib` |
| pre-event gate model | `models/m1_specialist/m1_fault_pre_event_logistic.joblib` |
| runtime metadata | `models/m1_specialist/m1_full_gate_runtime_policy_metadata.json` |
| source training inputs | `artifacts/m1_specialist/training_inputs/` |
| internal retrain registry | `output/reports/m1_internal_joblib_model_registry.csv` |

## 저장소 안에서 새로 만드는 것

| 항목 | 위치 |
|---|---|
| raw inventory/schema audit | `data/interim/` |
| M1 anomaly model/score | `models/anomaly/`, `output/anomaly_scores.csv` |
| merged model score | `output/merged_model_scores.csv` |
| final agent card | `output/agent_priority_card.csv` |
| M1 specialist parallel card | `output/agent/m1_specialist_parallel_agent_card.csv` |
| M1 hybrid final card | `output/agent/m1_agent_priority_card.csv` |
| validation/report evidence | `output/reports/` |
| comparison notebooks | `compare/` |

## 재학습 추적

`full_retrain` 실행 후 아래 파일로 실제 source 호출과 결과를 확인한다.

```text
output/reports/source_retrain_metadata.json
output/reports/m1_source_retrain_metadata.json
output/reports/retrain_logs/retrain_current_best.log
output/reports/retrain_logs/retrain_m1_specialist.log
```

기본 `full_retrain`은 현재 저장소의 내부 재학습 경로를 사용한다. 외부 source 프로젝트는 M1 학습 입력을 처음 bootstrap하거나 external retrain mode를 명시적으로 켰을 때만 필요하다.
# 2026-07-08 Internal Source Trace Update

The default source of the regenerated current-best body is now this repository:

- `output/risk_scores.csv`
- `output/leadtime_scores.csv`
- `output/priority_scores.csv`
- `models/risk/risk_model_best.joblib`
- `models/leadtime/leadtime_model_best.joblib`
- `models/priority/priority_engine_best_metadata.json`

The M1 specialist gate joblibs are regenerated from these package-local inputs:

- `artifacts/m1_specialist/training_inputs/m1_fault_gate_lock_predictions.csv`
- `artifacts/m1_specialist/training_inputs/m1_task_activity_window_candidate_predictions.csv`
- `artifacts/m1_specialist/training_inputs/m1_expansion_feature_pool.csv`
- `artifacts/m1_specialist/training_inputs/m1_compact_feature_set_summary.csv`
- `artifacts/m1_specialist/training_inputs/m1_gate_training_data.csv`

The old sibling source folders are no longer required for default `full_retrain` after those inputs exist. They are used only for first bootstrap or when `THIRD_MODEL_CURRENT_BEST_RETRAIN_MODE=external` or `THIRD_MODEL_M1_SPECIALIST_RETRAIN_MODE=external` is set.
