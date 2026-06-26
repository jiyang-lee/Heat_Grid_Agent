# 06 Risk / Leadtime experiment comparison summary

## 목적

현재 195개 feature contract를 유지한 상태에서, 06 risk / leadtime 성능 개선 후보를 한 번에 재실행하고 holdout 기준으로 비교했다.

이번 실험은 공식 모델을 교체하지 않고, 비교 산출물만 갱신했다.

## 재실행한 실험

### Risk audit

```text
python PREPROCESSING/osj/experiments/06_risk_audit.py --run all
```

포함 내용:

- false negative audit
- false negative deep audit
- feature importance audit
- group calibration
- drift feature ablation
- manufacturer2 SH false positive audit

### Risk feature experiments

```text
python PREPROCESSING/osj/experiments/06_risk_experiments.py --run all
```

포함 내용:

- event context re-encoding
- event state feature
- thermal relation feature
- state + thermal combined feature
- weighting experiment
- combined feature experiment

### Leadtime experiments

```text
python PREPROCESSING/osj/experiments/06_leadtime_experiments.py --run all
```

포함 내용:

- timeflow feature
- bucket redesign
- pseudo label refinement

## 생성한 비교 산출물

```text
report/experiment_comparison/risk_holdout_experiment_comparison.csv
report/experiment_comparison/risk_holdout_experiment_comparison_with_delta.csv
report/experiment_comparison/leadtime_holdout_experiment_comparison.csv
report/experiment_comparison/leadtime_holdout_experiment_comparison_with_delta.csv
report/experiment_comparison/experiment_summary.json
```

## Risk 결론

### 현재 공식 risk 기준

공식 모델:

```text
official_calibrated
```

holdout 성능:

```text
ROC-AUC  0.7628
AP       0.6197
Precision 0.5867
Recall    0.5116
F1        0.5466
FPR       0.1449
```

### 전체 risk 실험 중 최고 F1

전체 비교 결과, holdout F1 기준 최고는 여전히 공식 calibrated 모델이다.

```text
official_calibrated
F1     0.5466
Recall 0.5116
FPR    0.1449
```

즉 이번에 재실행한 event / thermal / combined / weighting / drift ablation 후보 중 공식 risk 모델을 교체할 후보는 없었다.

### 공식 모델에 가장 근접한 후보

| 후보 | F1 | Recall | Precision | FPR | 판단 |
|---|---:|---:|---:|---:|---|
| official_calibrated | 0.5466 | 0.5116 | 0.5867 | 0.1449 | 공식 유지 |
| official_base_raw | 0.5412 | 0.5349 | 0.5476 | 0.1776 | recall은 높지만 FPR 증가 |
| promoted_base | 0.5153 | 0.4884 | 0.5455 | 0.1636 | 공식보다 낮음 |
| promoted_calibrated | 0.5125 | 0.4767 | 0.5541 | 0.1542 | 공식보다 낮음 |
| leadtime_1_3d_x2_plus_group_x1_5 | 0.5025 | 0.5814 | 0.4425 | 0.2944 | recall은 높지만 FPR 과다 |

### Risk 판단

```text
Risk 공식본 교체: 보류
현재 공식본 유지: 예
```

이유:

- 공식 calibrated가 F1 기준 최고다.
- 일부 후보는 recall을 올렸지만 FPR이 너무 커진다.
- 운영 우선순위 시스템에서는 false positive가 커지면 urgent/high 쏠림이 재발할 수 있다.

## Risk audit에서 확인된 병목

### holdout false negative

holdout false negative:

```text
42건
```

holdout true positive:

```text
44건
```

false negative가 많이 몰린 그룹:

| group | false negative count | 평균 risk probability | 평균 anomaly score | 평균 estimated lead time |
|---|---:|---:|---:|---:|
| manufacturer 2 \| SH with buffer tank | 19 | 0.1738 | 0.4578 | 31.53h |
| manufacturer 2 \| SH + DHW | 8 | 0.2953 | 0.4207 | 42.68h |
| manufacturer 1 \| SH + DHW | 7 | 0.3106 | 0.4510 | 23.52h |
| manufacturer 2 \| SH | 6 | 0.4122 | 0.4528 | 51.20h |
| manufacturer 1 \| SH + DHW with sub-circuits | 2 | 0.1891 | 0.4511 | 33.82h |

### 가장 큰 병목

```text
manufacturer 2 | SH with buffer tank
```

이 그룹은 false negative 19건으로 가장 크고, 평균 risk probability가 0.1738로 낮다.
즉 anomaly score는 0.45 수준으로 낮지 않은데 risk 모델이 위험 패턴으로 충분히 올리지 못한다.

### feature contribution 관점 병목

false negative와 true positive의 contribution 차이가 큰 feature:

```text
days_since_last_any_event
p_net_return_temperature__max
s_dhw_upper_storage_temperature__last
s_dhw_3-way_valve_status__dominant__is__missing
doy_sin
anomaly_score
```

해석:

- event context가 false negative에서 충분히 위험 방향으로 작동하지 않는다.
- return temperature / DHW storage temperature 계열이 true positive에서는 강하지만 false negative에서는 약하다.
- 제조사/구성별 thermal relation 표현이 더 필요하다.

## Drift ablation 결론

실험 대상:

```text
day_of_year
days_since_last_any_event
p_net_supply_temperature__mean
p_net_supply_temperature__max
network_temperature_gap__mean
```

결론:

```text
drift 의심 feature를 단순 제거하는 것은 개선으로 이어지지 않았다.
```

이유:

- `drop_day_any_supply` 등 일부 제거 조합은 F1 0.4099 수준까지 하락했다.
- 단일 제거도 공식 calibrated보다 낮았다.
- 따라서 이 feature들은 삭제보다 재표현 또는 group-aware 보정이 맞다.

## Risk 다음 개선 방향

이번 결과 기준으로 risk 개선은 아래 방향이 맞다.

### 1. 공식 calibrated 유지

지금 바로 교체할 모델은 없다.

### 2. false negative 집중 개선

우선 대상:

```text
manufacturer 2 | SH with buffer tank
manufacturer 2 | SH + DHW
1-3d leadtime bucket
```

### 3. feature 삭제보다 재표현

단순 ablation은 실패했다.
따라서 아래처럼 바꾸는 쪽이 맞다.

```text
days_since_last_any_event -> event bucket / recent flag / no-history flag
p_net_return_temperature / supply temperature -> group normalized thermal gap
DHW storage temperature -> upper-lower gap, storage-supply gap
```

## Leadtime 결론

### 현재 공식 leadtime 기준

공식 모델:

```text
official_promoted
current_3bucket
```

holdout 성능:

```text
Accuracy   0.6512
Macro F1   0.4405
Weighted   0.6432
Top2 Acc   0.9651
Bucket MAE 0.3837
```

### 전체 leadtime 실험 중 최고 Macro F1

최고 macro F1은 2버킷 urgency 후보다.

```text
bucket_redesign::binary_24h_vs_1_7d
Accuracy  0.6163
Macro F1  0.6120
Weighted  0.6196
```

하지만 이 후보는 3버킷 메인 leadtime 모델을 대체하지 않는다.

이유:

- 2버킷은 문제를 단순화해서 macro F1이 오른다.
- `0-24h` vs `1-7d` 즉시성 판단에는 유리하다.
- 하지만 `1-3d`와 `3-7d` 구분 정보가 사라진다.

### Leadtime 판단

```text
메인 leadtime 3버킷: official_promoted 유지
2버킷 urgency: 보조 체인으로 추가 검토 가치 있음
4버킷: 파기 유지
label refinement: 효과 없음
```

## Leadtime 다음 개선 방향

### 1. 메인 3버킷은 유지

현재 3버킷 공식본은 accuracy / top2 / bucket MAE 기준으로 안정적이다.

### 2. 2버킷 urgency 보조모델 추가 검토

Priority Engine에서 아래 판단에 사용할 수 있다.

```text
오늘 또는 즉시 점검이 필요한가?
```

### 3. timeflow 추가 확장

현재 `timeflow_lag_delta_roll3`는 baseline보다 macro F1을 소폭 개선했다.

다음 후보:

```text
slope
rolling std
2~4 window 누적 변화량
anomaly_score 증가 속도
risk_probability 증가 속도
thermal gap 확대 속도
```

## 최종 판단

이번 전체 실험에서 바로 승격할 항목:

```text
없음
```

유지할 공식본:

```text
risk: data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
leadtime: data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv
priority: data/processed/ml_priority/priority_engine_scores_tuned.csv
```

다음에 실제로 구현할 가치가 가장 높은 항목:

```text
1. risk false negative 그룹 전용 feature 재표현
2. manufacturer/configuration-aware thermal gap feature
3. event context bucket + no-history/recent flag 재설계
4. leadtime 2버킷 urgency 보조체인
```

이번 실험의 핵심 결론:

```text
현재 공식 risk/leadtime 모델은 유지한다.
단순 feature 삭제나 기존 실험 후보로는 공식본을 넘지 못했다.
성능 개선은 새 feature를 무작정 추가하는 것이 아니라,
false negative가 몰린 그룹을 겨냥한 event/thermal 재표현으로 가야 한다.
```

