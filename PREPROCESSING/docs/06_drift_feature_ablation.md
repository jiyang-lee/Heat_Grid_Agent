# 06 drift feature ablation

## 목적

`06_feature_importance_audit`에서 drift 의심으로 분류된 feature를 실제로 제거했을 때 holdout이 좋아지는지 확인한다.

대상 후보:

```text
day_of_year
days_since_last_any_event
p_net_supply_temperature__mean
p_net_supply_temperature__max
network_temperature_gap__mean
```

## 실행 파일

```text
PREPROCESSING/osj/06_drift_feature_ablation.py
```

## 출력 파일

```text
data/processed/ml_risk/lgbm_risk_drift_feature_ablation.csv
data/processed/ml_risk/lgbm_risk_drift_feature_ablation_holdout.csv
```

## 실험 방식

- 기준 split: `split_event_regime_based`
- 기준 threshold: `high >= 0.44`
- 단일 제거와 조합 제거를 함께 비교

variant:

```text
baseline_v3
drop_day_of_year
drop_days_since_last_any_event
drop_supply_temp_mean_max
drop_network_temp_gap_mean
drop_top5_drift
drop_calendar_and_supply
drop_event_any_and_supply
drop_day_any_supply
```

## 현재 결과 해석

holdout 기준 상대적으로 나은 쪽은 아래 두 조합이다.

```text
drop_day_any_supply
drop_event_any_and_supply
```

특징:

- `precision`은 baseline보다 올라간다.
- `false_positive_rate`도 일부 감소한다.
- 하지만 `recall`이 같이 내려간다.
- 전체적으로 “명확한 승격”이라고 부를 정도의 개선은 아니다.

예시:

```text
drop_day_any_supply
- precision 0.4400
- recall    0.3837
- f1        0.4099
- fpr       0.1963
```

```text
drop_event_any_and_supply
- precision 0.4342
- recall    0.3837
- f1        0.4074
- fpr       0.2009
```

## 중요 주의사항

이번 ablation은 `06` 메인 노트북을 경량 재구성한 스크립트 기반 비교다.

즉:

- variant 간 상대 비교에는 쓸 수 있다.
- 하지만 현재 스크립트 baseline이 메인 `06` 공식 산출물과 완전히 일치하지는 않는다.

따라서 이번 결과만으로 곧바로 메인 feature set을 바꾸면 안 된다.

## 판단

### 바로 반영: 아니오

이유:

1. 메인 `06` 공식 baseline과 완전 일치 검증이 아직 부족하다.
2. 일부 후보 제거는 precision/FPR은 좋아져도 recall을 깎는다.
3. 현재로선 “이 feature는 반드시 빼야 한다” 수준의 강한 증거가 아니다.

### 다음 우선순위

```text
1. notebook-native 재현으로 top 2 조합 재검증
2. manufacturer 2 / SH 잔여 false positive 구간만 따로 score diff 확인
3. 그 뒤에만 메인 06 feature set 변경
```

## 현재 실무 결론

- `day_of_year`, `days_since_last_any_event`, `p_net_supply_temperature__mean/max`는 재검토 후보가 맞다.
- 하지만 지금 단계에서는 “삭제 후보”이지 “확정 삭제”는 아니다.
- 다음 수정은 전면 제거보다 `조건부 제외 실험` 또는 `group별 calibration`이 더 안전하다.
