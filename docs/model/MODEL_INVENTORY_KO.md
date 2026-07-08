# 모델 인벤토리

최종 agent card를 구성하는 모델 파일, score 산출물, 재학습 책임을 정리한 문서다.

## 전체 흐름

| 계열 | 역할 | 주요 파일 |
|---|---|---|
| current-best risk | pre_fault supervised 위험 확률과 risk level 제공 | `models/risk/risk_model_best.joblib`, `output/risk_scores.csv` |
| current-best leadtime | 가까운 이벤트 구간의 시간 긴급도 제공 | `models/leadtime/leadtime_model_best.joblib`, `output/leadtime_scores.csv` |
| current-best priority | risk/leadtime/context 기반 baseline priority 제공 | `models/priority/priority_engine_best_metadata.json`, `output/priority_scores.csv` |
| M1 anomaly | 정상 분포 이탈 evidence 제공 | `models/anomaly/`, `output/anomaly_scores.csv` |
| M1 specialist gates | fault/task/activity/pre-event 병렬 evidence 제공 | `models/m1_specialist/`, `output/m1_specialist_gate_scores.csv` |
| M1 hybrid priority | current-best priority와 M1 specialist priority 결합 | `output/m1_specialist_scores.csv`, `output/agent/m1_agent_priority_card.csv` |

## 모델 파일

| 폴더 | 파일 | 설명 |
|---|---|---|
| `models/anomaly/` | `standard_scaler.joblib` | M1 anomaly scaling |
| `models/anomaly/` | `isolation_forest.joblib` | M1 IsolationForest |
| `models/anomaly/` | `mahalanobis_ledoitwolf.joblib` | M1 Mahalanobis covariance |
| `models/anomaly/` | `anomaly_metadata.json` | anomaly feature/threshold metadata |
| `models/risk/` | `risk_model_best.joblib` | current-best risk 모델 본체 |
| `models/risk/` | `risk_model_best_metadata.json` | current-best risk metadata |
| `models/leadtime/` | `leadtime_model_best.joblib` | current-best leadtime 모델 본체 |
| `models/leadtime/` | `leadtime_model_best_metadata.json` | current-best leadtime metadata |
| `models/priority/` | `priority_engine_best_metadata.json` | current-best priority metadata |
| `models/m1_specialist/` | `m1_*_gate_*.joblib` | M1 specialist gate 모델 |
| `models/m1_specialist/` | `m1_full_gate_runtime_policy_metadata.json` | M1 gate runtime policy |

## Current-Best 책임

`risk_model_best.joblib`와 `leadtime_model_best.joblib`는 원천 current-best 프로젝트가 학습한다. 이 저장소는 `retrain_current_best` 단계에서 원천 파이프라인을 호출하고, 모델/metadata/score를 현재 저장소로 가져온다.

```powershell
uv run third-model-pipeline --steps retrain_current_best
```

기본 원천 step:

```text
anomaly, multi_window_anomaly, risk, leadtime, priority, report, ops_eval
```

`raw_ae`는 최종 M1 agent card 계약에 들어가지 않은 실험 branch라 기본 재학습에서 제외한다. 필요하면 `THIRD_MODEL_INCLUDE_RAW_AE=1` 또는 `THIRD_MODEL_RETRAIN_CURRENT_BEST_STEPS`로 명시한다.

## M1 Specialist 책임

M1 specialist source는 네 개 gate 모델을 만든다.

| 모델 | 파일 | threshold | 주의 |
|---|---|---:|---|
| fault gate | `m1_fault_gate_rf_depth3.joblib` | 0.50 | evidence threshold |
| task gate | `m1_task_gate_rf_depth3.joblib` | 0.50 | native label 성능 claim 제한 |
| activity gate | `m1_activity_gate_rf_depth3.joblib` | 0.50 | native label 성능 claim 제한 |
| pre-event gate | `m1_fault_pre_event_logistic.joblib` | 0.60 | event 선행 evidence |

```powershell
uv run third-model-pipeline --steps retrain_m1_specialist
```

M1 source는 `05_데이터셋/PreDist/predist_dataset.zip`을 요구한다. 없으면 `THIRD_MODEL_PREDIST_ZIP_PATH` 또는 `../HeatGrid_Agent/data/_downloads/predist_dataset.zip`에서 찾아 source 폴더로 복사한다.

## Anomaly 기준

| 구성 | 설명 |
|---|---|
| train 기준 | M1 train split 중 normal window |
| score | IsolationForest ratio, Mahalanobis ratio |
| active policy | `IF ratio >= 0.90 AND Mahalanobis ratio >= 1.00` |
| criticality | active anomaly persistence counter, 최종 evidence 기준 `>= 5` |

근거 파일:

```text
compare/m1_threshold_weight_rationale_report.ipynb
output/reports/anomaly_if_mahalanobis_policy_grid.csv
output/reports/anomaly_criticality_threshold_sweep.csv
```

## Priority 결합

M1 specialist 내부 priority:

```text
m1_specialist_priority_score
= 100 * (
    0.55 * pre_event_probability
  + 0.30 * leadtime_urgency
  + 0.15 * fault_group_weight
)
```

최종 hybrid priority:

```text
m1_hybrid_priority_score
= 0.65 * current_best_priority_score
 + 0.35 * m1_specialist_priority_score
```

`0.65 / 0.35`는 metric-only best가 아니라 운영 선택점이다. 비교 근거는 다음 파일에 있다.

```text
output/reports/hybrid_selected_weight_comparison.csv
output/reports/hybrid_weight_sweep.csv
compare/m1_threshold_weight_rationale_report.ipynb
```

## Scope 제한

- 현재 검증은 M1 중심이다.
- M2나 전체 제조사에 그대로 일반화하지 않는다.
- M2 적용 시 별도 calibration, validation, feature coverage 점검이 필요하다.
- risk/leadtime model 파일은 포함되어 있지만, 기본 `all` 실행은 current-best score bridge를 사용한다. 새 raw window부터 standalone inference를 닫으려면 raw/canonical/feature 재생성 계약까지 확인해야 한다.
