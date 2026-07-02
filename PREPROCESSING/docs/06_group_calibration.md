# 06 group calibration

## 목적

`manufacturer 2 / SH` holdout 정상 구간에서 잔여 false positive가 집중되어 있으므로,
전역 feature 삭제 대신 `group-specific threshold override`를 운영 레이어에 추가한다.

핵심 아이디어:

```text
risk_probability는 그대로 유지
high/critical 판정 기준만 특정 그룹에서 더 엄격하게 적용
```

## 실행 파일

```text
PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
```

## 출력 파일

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
data/processed/ml_risk/lgbm_risk_metrics_calibrated.csv
data/processed/ml_risk/lgbm_group_threshold_overrides.csv
data/processed/ml_risk/models/risk_model_group_calibration.json
```

## 적용 규칙

기본 threshold:

```text
medium >= 0.22
high >= 0.44
critical >= 0.90
```

group override:

```text
manufacturer 2 + SH:
  high >= 0.78
  medium >= 0.22
  critical >= 0.90
```

선정 기준:

- `manufacturer 2 / SH` validation 분포만 사용
- validation에서 normal false positive를 0으로 만들면서
- recall을 과하게 깎지 않는 threshold 선택

## 결과

### 전체 holdout

보정 전:

```text
precision 0.5476
recall    0.5349
f1        0.5412
fpr       0.1776
```

보정 후:

```text
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449
```

해석:

- precision 상승
- false positive rate 하락
- recall은 소폭 하락
- 전체 holdout F1은 소폭 개선

### manufacturer 2 / SH holdout

보정 후:

```text
precision 0.6000
recall    0.5000
f1        0.5455
fpr       0.0755
```

핵심은 이 그룹의 false positive rate가 많이 줄었다는 점이다.

## 왜 이 방식이 맞는가

현재 오탐 원인은 전역적으로 무의미한 feature 하나보다는,

```text
event-context + thermal-gap 조합이
특정 그룹에서 과민하게 작동하는 것
```

에 가깝다.

따라서 지금 단계에서는

```text
전역 feature 삭제
```

보다

```text
group-aware operating threshold
```

가 더 안전하고 바로 적용 가능하다.

## 운영 적용 포인트

Priority Engine 또는 Agent에서는 아래 순서를 따른다.

```text
1. risk_probability는 base model 출력 사용
2. manufacturer/configuration 조합 확인
3. override가 있으면 group threshold 적용
4. risk_level_calibrated 기준으로 우선순위 판단
```

즉 운영판단은 `risk_level_calibrated`를 우선 사용하고,
원본 score는 그대로 보존한다.

## 2026-06-25 Promotion Follow-up

후속 보강 실험에서

```text
overall winner:
  thermal_group_zscore_only

problem-group winner:
  event_context_only
```

가 각각 더 나은 후보로 나왔지만,
이를 하이브리드 승격안으로 만들었을 때 overall holdout이 현재 calibrated 운영본보다 더 좋아지지 않았다.

따라서 현재 시점에서는 group calibration 체인을 계속 공식 운영본으로 유지한다.

공식본:

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
data/processed/ml_risk/lgbm_risk_metrics_calibrated.csv
```

승격 검토 후보:

```text
data/processed/ml_risk/lgbm_risk_scores_promoted.csv
data/processed/ml_risk/lgbm_risk_metrics_promoted.csv
```

