# 06 promotion decision

## 목적

06 보강 실험에서 나온 후보를 실제 메인 06 산출물로 승격할 수 있는지 판단한 기록이다.

이번 단계에서 확인한 핵심은 단순하다.

- `overall`에서 가장 안정적인 후보와
- `manufacturer 2 / SH` 문제 그룹에서 가장 좋은 후보가

서로 달랐다.

그래서 아래 두 가지를 각각 택해 하이브리드 승격안을 만들었다.

```text
overall:
  thermal_group_zscore_only

manufacturer 2 / SH:
  event_context_only
```

## 실행 파일

```text
PREPROCESSING/osj/06_promoted_risk_model.py
```

## 출력 파일

```text
data/processed/ml_risk/lgbm_risk_scores_promoted.csv
data/processed/ml_risk/lgbm_risk_metrics_promoted.csv
data/processed/ml_risk/lgbm_risk_thresholds_promoted.csv
data/processed/ml_risk/lgbm_group_threshold_overrides_promoted.csv
data/processed/ml_risk/models/lightgbm_risk_model_promoted_overall.joblib
data/processed/ml_risk/models/lightgbm_risk_model_promoted_manufacturer2_sh.joblib
data/processed/ml_risk/models/risk_model_promoted_metadata.json
```

## 비교 기준

비교 대상은 두 개다.

### 현재 공식 운영본

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
data/processed/ml_risk/lgbm_risk_metrics_calibrated.csv
```

### 승격 후보 하이브리드본

```text
data/processed/ml_risk/lgbm_risk_scores_promoted.csv
data/processed/ml_risk/lgbm_risk_metrics_promoted.csv
```

## 결과

### 현재 공식 운영본 holdout overall

```text
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449
roc_auc   0.7628
ap        0.6197
```

### 승격 후보 하이브리드본 holdout overall

```text
precision 0.5541
recall    0.4767
f1        0.5125
fpr       0.1542
roc_auc   0.7271
ap        0.5485
```

### manufacturer 2 / SH holdout

승격 후보 하이브리드본은 문제 그룹 자체에서는 괜찮다.

```text
precision 1.0000
recall    0.4167
f1        0.5882
fpr       0.0000
roc_auc   0.8852
ap        0.7505
```

하지만 메인 06 승격 판단은 전체 holdout 기준이 우선이다.

## 결론

이번 승격안은 공식본으로 채택하지 않는다.

이유:

```text
문제 그룹은 개선되지만
overall holdout이 현재 공식 calibrated 체인보다 나빠진다.
```

따라서 현재 공식 06 산출물은 그대로 유지한다.

## 현재 공식본

downstream에서 계속 사용할 공식본:

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
risk_level_calibrated
```

## 이번 작업의 의미

이번 결과는 실패가 아니라 경계선 확정이다.

확정된 내용:

1. `event_context_only`는 문제 그룹 보강 방향으로 유효하다.
2. `thermal_group_zscore_only`는 전체 일반화 보강 후보로 의미가 있다.
3. 하지만 두 후보를 지금 바로 메인 06 공식본으로 결합 승격하면 안 된다.

## 다음 단계

다음은 다시 전체 재학습 승격이 아니라, 아래 순서가 맞다.

```text
1. 현재 공식 calibrated 체인을 유지
2. 07 Priority Engine과 08 Agent는 계속 calibrated 공식본 기준으로 연결
3. 이후 risk false negative audit / event-context / thermal feature를 더 좁혀서 재설계
```
