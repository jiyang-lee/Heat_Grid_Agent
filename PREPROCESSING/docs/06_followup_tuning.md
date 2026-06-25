# 06-B. follow-up tuning summary

이 문서는 03/04/06 보강 이후 추가로 수행한 잔여 오탐 audit, ablation, threshold 재조정, leadtime 3버킷 비교 결과를 정리한다.

## 1. manufacturer 2 / SH 잔여 오탐

primary split `split_event_regime_based` 기준 holdout에서 `manufacturer 2 / SH` 잔여 false positive는 총 13건이다.

분포:

```text
substation 11: 9건
substation 59: 4건
```

관련 산출물:

```text
data/processed/ml_risk/manufacturer2_sh_residual_false_positives.csv
data/processed/ml_risk/manufacturer2_sh_residual_false_positive_summary.csv
```

해석:

- 전체 holdout false positive는 많이 줄었지만, `manufacturer 2 / SH`는 아직 특정 기계실에 오탐이 몰린다.
- 다음 audit은 `substation 11`, `substation 59`의 계절/운전상태 context를 따로 보는 방향이 적절하다.

## 2. quick ablation

빠른 follow-up ablation은 현재 v3 feature 집합을 기준으로 재구성한 실험이다.
절대 수치보다 “어떤 feature 묶음이 기여하는가”를 보는 용도다.

산출물:

```text
data/processed/ml_risk/lgbm_risk_followup_ablation.csv
```

핵심 결과:

```text
no_control_onehot:
  holdout F1 0.3669

full_v3:
  holdout F1 0.3956

no_event_days:
  holdout F1 0.4194

no_cyclic_time:
  holdout F1 0.5048
```

판단:

- control/status one-hot 제거는 성능을 악화시킨다.
- event days 제거도 holdout 분리력을 약화시킨다.
- cyclic time 제거 실험은 reconstructed quick run 기준으로는 F1이 높게 나왔지만, false positive rate가 0.3318로 더 높다.
- 따라서 cyclic time은 운영상 제거 후보라기보다 threshold와 함께 다시 조정할 대상이다.

## 3. threshold follow-up

산출물:

```text
data/processed/ml_risk/lgbm_risk_threshold_followup_comparison.csv
data/processed/ml_risk/lgbm_risk_threshold_followup_candidates.csv
```

후보:

```text
0.42:
  validation F1 0.7361
  holdout F1 0.5475
  holdout FPR 0.2056

0.44:
  validation F1 0.7324
  holdout F1 0.5412
  holdout FPR 0.1776
```

권장 운영 threshold:

```text
high >= 0.44
medium >= 0.22
critical >= 0.90
```

이유:

- 기존 `high >= 0.40` 대비 holdout false positive rate를 더 줄인다.
- holdout F1도 유지되거나 약간 개선된다.
- priority engine에서 과도한 경보를 줄이는 방향에 더 맞는다.

## 4. leadtime 3버킷

기존 4버킷:

```text
0-6h
6-24h
1-3d
3-7d
```

비교용 3버킷:

```text
0-24h
1-3d
3-7d
```

산출물:

```text
data/processed/ml_leadtime/leadtime_bucket_3_scores.csv
data/processed/ml_leadtime/leadtime_bucket_3_metrics.csv
data/processed/ml_leadtime/models/lightgbm_leadtime_bucket_3_model.joblib
data/processed/ml_leadtime/models/leadtime_bucket_3_model_metadata.json
```

holdout 비교:

```text
기존 4버킷:
  accuracy 0.5814
  macro F1 0.3371
  top2 0.8837
  bucket MAE 0.5349

3버킷:
  accuracy 0.6163
  macro F1 0.4118
  top2 0.9651
  bucket MAE 0.4186
```

판단:

- 현재 데이터셋에서는 4버킷보다 3버킷이 더 안정적이다.
- 운영용 leadtime은 우선 3버킷을 기본 후보로 두는 것이 타당하다.

## 5. 운영 규칙 초안

현재 추천 조합:

```text
high risk (>= 0.44) + leadtime 0-24h
  -> 즉시 우선 점검

high risk (>= 0.44) + leadtime 1-3d
  -> 단기 점검 후보

medium risk (>= 0.22) + leadtime 0-24h
  -> 빠른 모니터링 / 전화 확인

medium risk (>= 0.22) + leadtime 1-3d or 3-7d
  -> 모니터링 큐

low risk
  -> 일반 모니터링
```

## 6. 다음 작업

우선순위:

1. `manufacturer 2 / SH`의 `substation 11`, `59` 개별 context audit
2. risk model에서 threshold `0.44` 운영 반영 여부 결정
3. leadtime 기본 모델을 3버킷 기준으로 승격할지 결정
4. 이후 07/08 연결
