# 06. legacy LightGBM risk and lead-time model 문서

이 문서는 `PREPROCESSING/osj/06_test/06_risk_leadtime_model.ipynb`에서 구현한 기존 LightGBM 기반 위험도 모델을 정리한다.

현재 이 문서는 메인 `Isolation Forest + LightGBM` 06 체인 문서다.

## 목적

이 노트북의 원래 목적은 Isolation Forest가 찾은 이상징후가 `faults.csv`의 고장신고 전 위험 패턴과 유사한지 판단하는 것이었다.

현재 위치:

- 현재 프로젝트의 위험도 / 진단 유사도 / 의사 리드타임 추정 기본 체인
- `window + LightGBM` 접근의 재현 가능한 기준 구현
- Agent / Priority Engine 계약과 연결되는 메인 참고 자료

ML은 고장을 확정하지 않는다. LightGBM 결과는 “고장 확률”이 아니라 “고장신고 전 위험 패턴과의 유사도” 또는 “위험 가능성”으로 해석한다.

## 모델 구조

전체 구조:

```text
sensor_features
+ isolation_forest_anomaly_score
+ fault_window_label
+ disturbance_history_features
-> LightGBM
-> risk_score / risk_probability
```

역할 구분:

```text
Isolation Forest:
  정상 패턴과 다른 이상징후를 찾는다.

LightGBM:
  그 이상징후가 고장신고 전 위험 패턴과 가까운지 판단한다.
```

## 입력

```text
data/processed/ml_features/trainable_windows.csv
data/processed/ml_features/feature_columns.csv
data/processed/ml_features/metadata_columns.csv
data/processed/ml_baseline/anomaly_baseline_scores.csv
data/processed/ml_windows/ml_window_dataset.csv
```

`ml_window_dataset.csv`는 training-control column을 다시 merge하기 위해 사용한다. 단, 다음 control column은 모델 feature로 넣지 않는다.

```text
normal_reference_*
use_for_supervised_training
window_source_type
normal_event_related
fault_event_id
fault_label
estimated_lead_time_hours
```

## 라벨 기준

`faults.csv`의 고장신고 시점을 기준으로 고장신고 전 일정 구간을 `pre_fault`로 본다.

```text
fault_report_time - 72h <= window_end <= fault_report_time
```

주의:

- `faults.csv` 시점은 실제 고장 발생 시점이 아니라 신고 시점이다.
- 따라서 “고장 발생 예측”이 아니라 “고장신고 전 위험 패턴 유사도 판단”으로 표현한다.
- 같은 fault event가 train/validation/holdout에 갈라지지 않도록 event split을 사용한다.
- pre_fault row는 `fault_event_id` 단위로 split한다.
- legacy 비교용 `split_event_based`에서는 normal row가 기존 `split_time_based`를 유지한다.
- primary 평가용 `split_event_regime_based`에서는 normal row가 `split_regime_based`를 사용한다.

## feature 구성

포함:

- 04번에서 선택한 센서 통계 feature
- 변화량, 이동평균, 변동성 계열 feature
- 05번 Isolation Forest의 `anomaly_score`
- `disturbances.csv` 기반 최근 정비/작업 이력 feature

제외:

- `anomaly_label`: threshold 기반 이진값이므로 제외
- `p_net_meter_energy`, `p_net_meter_volume`의 절대 누적값 proxy
- fault id, fault label, lead time 같은 정답 또는 출처에 가까운 column
- normal reference filter 관련 control column

## 출력

```text
data/processed/ml_risk/lgbm_risk_scores.csv
data/processed/ml_risk/lgbm_risk_metrics.csv
data/processed/ml_risk/lgbm_risk_thresholds.csv
data/processed/ml_risk/lgbm_threshold_selection.csv
data/processed/ml_risk/lgbm_feature_importance.csv
data/processed/ml_risk/event_split_leakage_audit.csv
data/processed/ml_risk/lgbm_run_consistency.csv
data/processed/ml_risk/models/lightgbm_risk_model.joblib
data/processed/ml_risk/models/risk_model_metadata.json
```

Agent와 Priority Engine이 사용할 최소 필드:

```text
substation_id
window_end
anomaly_score
risk_score
risk_probability
risk_level
main_abnormal_features
related_fault_history
related_disturbance_history
model_explanation_features
```

## 현재 설정

현재 사용 모델:

```text
model_version: lgbm_risk_06_event_days_v3
primary_split: split_event_regime_based
feature_count: 189
```

threshold:

```text
medium >= 0.22
high >= 0.44
critical >= 0.90
```

??? threshold? follow-up tuning ??? ??? ????. ?? ?? 06 ???? `medium=0.22`, `high=0.44`, `critical=0.90`? ????.

## 실행 순서

의존 관계 때문에 다음 순서로 실행한다.

```text
04_feature_selection
05_baseline_anomaly_model
06_risk_leadtime_model
06_risk_leadtime_audit
```

최종 clean run row consistency:

```text
trainable_windows: 2555
anomaly_scores: 2555
modeling_df: 2526
risk_scores_df: 2526
```

## event context 보강

`manufacturer 2 / SH` holdout normal이 과거 fault/task 이후 구간이라는 점을 반영하기 위해 과거 이벤트 맥락 feature를 추가했고, 보강 후에는 03/04에서 만든 cyclic time과 one-hot categorical feature를 그대로 받아 regime 차이를 직접 반영한다.

중요한 제한:

- 미래 fault까지 남은 시간은 feature로 쓰지 않는다.
- feature는 `window_start` 이전에 발생한 fault/task만 사용한다.
- 평가 row는 줄이지 않는다.

모델 입력에 추가한 feature:

```text
days_since_last_fault_event
days_since_last_task_event
days_since_last_any_event
hour_sin
hour_cos
dow_sin
dow_cos
doy_sin
doy_cos
manufacturer__is__*
configuration_type__is__*
season_bucket__is__*
```

비교 산출물:

```text
data/processed/ml_risk/lgbm_event_context_comparison.csv
data/processed/ml_risk/lgbm_event_context_ablation.csv
data/processed/ml_risk/lgbm_event_context_ablation_group_summary.csv
data/processed/ml_risk/lgbm_event_context_ablation_feature_importance.csv
```

`recent_*` flag까지 모두 넣은 full context보다, 경과일 3개만 넣은 `event_days_only`가 더 보수적이었다. holdout F1은 full context보다 약간 낮지만 ROC-AUC가 더 높고 false positive rate가 낮아 현재 canonical으로 채택했다.

## 최종 성능

primary split 기준:

```text
train:
  rows 1631
  ROC-AUC 1.0000
  AP 1.0000
  precision 1.0000
  recall 1.0000
  F1 1.0000

validation:
  rows 431
  ROC-AUC 0.7786
  AP 0.7919
  precision 0.7260
  recall 0.7413
  F1 0.7336

holdout:
  rows 300
  ROC-AUC 0.7628
  AP 0.6197
  precision 0.4949
  recall 0.5698
  F1 0.5297
```

legacy `split_event_based` 비교:

```text
validation F1: 0.7970
holdout ROC-AUC: 0.7724
holdout F1: 0.5131
holdout false positive rate: 0.2231
```

보강 후 핵심 변화는 false positive rate 하락이다.
특히 primary split holdout 기준 false positive rate가 `0.6104 -> 0.2336` 수준으로 낮아졌다.

holdout 평균 risk는 여전히 pre_fault가 normal보다 높다.

```text
holdout normal mean risk: 0.5368
holdout pre_fault mean risk: 0.6652
```

다만 train ROC-AUC/AP가 여전히 1.0이고, primary split과 legacy split의 holdout 차이도 남아 있으므로 현재 모델은 운영 확정 모델이 아니라 regime-aware event-days guarded baseline이다.

## 현재 한계

현재 실패 양상은 단순 overfitting만으로 설명하기 어렵다.

확인된 원인:

- legacy split에서는 train이 event 단위로 분리됐지만, normal row는 time split 기반이라 normal 분포가 split별로 다르다.
- holdout normal 중 `manufacturer 2 / SH`가 train normal과 열적 분포가 크게 다르다.
- `manufacturer 2 / SH` holdout normal은 substation 11, 59이고, holdout pre_fault는 substation 45라 같은 group 안에서도 기계실 구성이 갈린다.
- threshold 조정과 group calibration만으로 false positive가 충분히 줄지 않는다.
- event days, cyclic time, one-hot categorical을 넣은 뒤에도 `manufacturer 2 / SH` holdout normal risk는 audit이 계속 필요하다.

현재 노트북에서는 이 문제를 줄이기 위해 `split_event_regime_based`를 추가 저장한다.
즉 normal row를 `manufacturer + configuration_type + season_bucket` 레짐 기준 split으로 바꾼 primary 평가축과, 기존 `split_event_based` legacy 비교축을 함께 남긴다.

`manufacturer 2 / SH` 최신 결과:

```text
holdout normal:
  substation 11: mean risk 0.9270
  substation 59: mean risk 0.9285

holdout pre_fault:
  substation 45: mean risk 0.9178
```

## 현재 상태

paper-aligned 전환 시도 자료는 현재 메인 문서가 아니다.

현재 판단:

- 전체 holdout은 보강으로 일부 개선됐지만, `manufacturer 2 / SH` normal 문제는 남아 있다.
- 이 문제는 window classification 기반 label/split/regime shift 한계로 본다.
- paper-aligned 전환 시도 자료는 `PREPROCESSING/legacy` 아래에 보존한다.

## 다음 단계

다음 단계는 이 06 체인을 기준으로 07/08 연결 또는 진단/리드타임 보강을 진행하는 것이다.

우선순위:

1. `PREPROCESSING/legacy/osj/06_paper_aligned_review`
2. `PREPROCESSING/legacy/osj/06_paper_aligned_data_selection`
3. `PREPROCESSING/legacy/osj/06_paper_aligned_autoencoder`
4. `PREPROCESSING/legacy/osj/06_paper_aligned_event_eval`
5. `PREPROCESSING/legacy/osj/06_paper_aligned_agent_contract`

## 2026-06-25 Promotion Decision

메인 06 승격 후보를 별도로 다시 검토했다.

핵심 판단:

```text
overall winner:
  thermal_group_zscore_only

manufacturer 2 / SH winner:
  event_context_only
```

위 둘을 분리 적용한 하이브리드 승격안도 만들었지만,
overall holdout 기준으로 현재 공식 calibrated 체인보다 성능이 낮았다.

비교:

```text
official calibrated holdout overall
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449

promoted hybrid holdout overall
precision 0.5541
recall    0.4767
f1        0.5125
fpr       0.1542
```

따라서 메인 06 공식본은 교체하지 않는다.

공식 downstream 입력:

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
risk_level_calibrated
```

승격 검토 기록:

```text
PREPROCESSING/docs/06_promotion_decision.md
PREPROCESSING/osj/06_promoted_risk_model.py
```
