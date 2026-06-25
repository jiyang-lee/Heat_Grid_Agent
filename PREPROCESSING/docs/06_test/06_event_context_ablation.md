# 06-B. legacy event context ablation 문서

이 문서는 `PREPROCESSING/osj/06_test/06_event_context_ablation.ipynb`의 목적과 결과를 정리한다.

현재 이 문서는 메인 `Isolation Forest + LightGBM` 06 체인 내부의 event context 보강 비교 기록이다.

## 목적

06번 LightGBM 모델에 추가한 과거 fault/task event context feature가 실제로 holdout 일반화에 도움이 되는지 확인한다.

비교 원칙:

- 메인 `lgbm_risk_scores.csv`는 덮어쓰지 않는다.
- 모든 variant는 같은 row, 같은 split, 같은 LightGBM 설정으로 비교한다.
- threshold는 각 variant의 event validation split에서 F1이 가장 높은 값을 선택한다.
- 미래 fault까지 남은 시간은 feature로 사용하지 않는다.

## 입력

```text
data/processed/ml_features/trainable_windows.csv
data/processed/ml_windows/ml_window_dataset.csv
data/processed/ml_features/feature_columns.csv
data/processed/ml_baseline/anomaly_baseline_scores.csv
data/processed/label_alignment/fault_alignment.csv
data/processed/label_alignment/disturbance_alignment.csv
```

## 출력

```text
data/processed/ml_risk/lgbm_event_context_ablation.csv
data/processed/ml_risk/lgbm_event_context_ablation_group_summary.csv
data/processed/ml_risk/lgbm_event_context_ablation_feature_importance.csv
```

## 비교 variant

```text
guarded_no_event_context
event_days_only
event_flags_only
event_fault_only
event_task_any_only
event_context_full
```

## holdout 결과

```text
event_flags_only:
  ROC-AUC 0.5488
  F1 0.4565
  FPR 0.9176

event_fault_only:
  ROC-AUC 0.5000
  F1 0.4165
  FPR 0.8839

event_task_any_only:
  ROC-AUC 0.5442
  F1 0.4131
  FPR 0.4944

event_context_full:
  ROC-AUC 0.5628
  F1 0.4025
  FPR 0.5393

event_days_only:
  ROC-AUC 0.5762
  F1 0.3932
  FPR 0.4757

guarded_no_event_context:
  ROC-AUC 0.4469
  F1 0.3641
  FPR 0.7828
```

## 판단

`event_flags_only`는 holdout F1이 가장 높지만 false positive rate가 0.9176으로 너무 높다. 운영 후보로 부적합하다.

`event_context_full`은 F1은 `event_days_only`보다 높지만 false positive rate도 더 높다.

`event_days_only`는 현재 06 체인에서 가장 보수적인 variant였다.

legacy 최종 보존 variant:

```text
model_version: lgbm_risk_06_event_days_v2
model event context features:
- days_since_last_fault_event
- days_since_last_task_event
- days_since_last_any_event
```

## 남은 문제

`manufacturer 2 / SH` holdout normal은 여전히 높은 risk를 받는다.

```text
holdout normal:
  substation 11 mean risk: 0.9270
  substation 59 mean risk: 0.9285

holdout pre_fault:
  substation 45 mean risk: 0.9178
```

따라서 이 문서의 결론은 “어떤 event context가 현재 06 체인에 더 맞는가”를 비교 근거로 남기자는 것이다.

paper-aligned 전환 시도 자료는 `PREPROCESSING/legacy` 아래에 별도 보존한다.
