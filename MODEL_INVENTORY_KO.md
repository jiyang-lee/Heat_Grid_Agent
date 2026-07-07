# 모델 인벤토리

## 최종 운영 흐름

최종 agent card는 세 계열을 결합한다.

| 계열 | 역할 | 주요 파일 |
|---|---|---|
| current-best risk | pre_fault supervised 위험 확률과 risk level 제공 | `models/risk/risk_model_best.joblib`, `output/risk_scores.csv` |
| current-best leadtime | 가까운 고장/정비 구간의 시간 긴급도 제공 | `models/leadtime/leadtime_model_best.joblib`, `output/leadtime_scores.csv` |
| current-best priority | risk/leadtime/context 기반 baseline priority 제공 | `models/priority/priority_engine_best_metadata.json`, `output/priority_scores.csv` |
| M1 anomaly | 정상 분포 이탈 evidence 제공 | `models/anomaly/`, `output/anomaly_scores.csv` |
| M1 specialist gates | fault/task/activity/pre-event M1 단독 병렬 evidence 제공 | `models/m1_specialist/`, `output/m1_specialist_gate_scores.csv` |
| M1 hybrid priority | current-best priority와 M1 specialist priority 결합 | `output/m1_specialist_scores.csv`, `output/agent/m1_agent_priority_card.csv` |

## Current-Best 모델

`risk_model_best.joblib`와 `leadtime_model_best.joblib`는 원천 current-best 프로젝트가 학습한다. 저장소는 `retrain_current_best` 단계에서 원천 파이프라인을 호출한 뒤 모델과 metadata를 `models/risk`, `models/leadtime`, `models/priority`로 복사한다.

재학습 명령:

```powershell
uv run python run_3rd_model_pipeline.py --steps retrain_current_best
```

원천 실행 step:

```text
anomaly, multi_window_anomaly, risk, leadtime, priority, report, ops_eval
```

`raw_ae`는 최종 M1 agent card 계약에 들어가지 않은 실험 branch라 기본 재학습에서 제외한다. 필요하면 `THIRD_MODEL_INCLUDE_RAW_AE=1` 또는 `THIRD_MODEL_RETRAIN_CURRENT_BEST_STEPS`로 명시한다.

## M1 Specialist 모델

M1 specialist source는 네 개 gate 모델을 만든다.

| 모델 | 파일 | threshold |
|---|---|---:|
| fault gate | `m1_fault_gate_rf_depth3.joblib` | 0.50 |
| task gate | `m1_task_gate_rf_depth3.joblib` | 0.50 |
| activity gate | `m1_activity_gate_rf_depth3.joblib` | 0.50 |
| fault pre-event gate | `m1_fault_pre_event_logistic.joblib` | 0.60 |

재학습 명령:

```powershell
uv run python run_3rd_model_pipeline.py --steps retrain_m1_specialist
```

M1 source는 `05_데이터셋/PreDist/predist_dataset.zip`을 요구한다. 저장소는 source에 zip이 없으면 `THIRD_MODEL_PREDIST_ZIP_PATH` 또는 `../HeatGrid_Agent/data/_downloads/predist_dataset.zip`에서 찾아 source 폴더로 복사한다.

## Anomaly 모델

저장소 안에서 M1 train-normal window를 기준으로 직접 재학습한다.

| 구성 | 설명 |
|---|---|
| StandardScaler | train-normal feature scaling |
| IsolationForest | local 이상 패턴 탐지 |
| LedoitWolf Mahalanobis | 공분산 기반 전역 거리 |
| active policy | `IF ratio >= 0.90 AND Mahalanobis ratio >= 1.00` |
| criticality | active anomaly persistence counter, 최종 evidence 기준 `>= 5` |

IF/Mahalanobis threshold grid와 criticality 1~10 sweep은 `compare/m1_threshold_weight_rationale_report.ipynb`, `output/reports/anomaly_if_mahalanobis_policy_grid.csv`, `output/reports/anomaly_criticality_threshold_sweep.csv`에 있다.

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

`0.65 / 0.35`는 무조건적인 metric 최적점이 아니라, validation 안정성, current-best baseline 유지, M1 specialist 반영률을 함께 본 운영 선택점이다. `0.72 / 0.28`, `0.90 / 0.10` 비교는 `output/reports/hybrid_selected_weight_comparison.csv`와 notebook에 남긴다.

## Scope 제한

현재 검증은 M1 중심이다. M2나 다른 제조사에 그대로 일반화하지 않는다. M2 적용은 별도 calibration, validation, feature coverage 점검이 필요하다.
