# 05 Isolation Forest feature / hyperparameter experiment summary

## 목적

초기 195개 feature contract는 수정하지 않고, Isolation Forest 모델의 입력 feature subset과 hyperparameter만 바꿔 score 자체 성능 개선 가능성을 확인했다.

공식 05 산출물은 덮어쓰지 않았다.

## 실행 파일

```text
PREPROCESSING/osj/experiments/06_test/05_iforest_feature_hyperparam_experiment.py
```

실행 명령:

```bash
python PREPROCESSING/osj/experiments/06_test/05_iforest_feature_hyperparam_experiment.py
```

## 생성 산출물

```text
report/experiment_comparison/iforest_feature_hyperparam_metrics.csv
report/experiment_comparison/iforest_feature_hyperparam_summary.csv
report/experiment_comparison/iforest_feature_hyperparam_detail.json
```

## 실험 원칙

고정:

```text
data/processed/ml_features/feature_columns.csv
data/processed/ml_baseline/models/baseline_model_metadata.json
195개 selected_feature_columns
```

변경:

```text
Isolation Forest 실험 입력 subset
Isolation Forest hyperparameter
```

즉, 이번 실험은 195개 feature contract를 바꾼 것이 아니라, 모델 실험 layer에서 입력 조합만 비교한 것이다.

## 기준 모델

공식 05 기준:

```text
feature_set: contract_195_full
param_set: default_300_auto
feature_count: 195
n_estimators: 300
contamination: auto
max_samples: auto
max_features: 1.0
bootstrap: False
```

split_time_based holdout 성능:

```text
ROC-AUC            0.7152
Average Precision 0.6930
Precision          1.0000
Recall             0.1278
F1                 0.2267
FPR                0.0000
```

## 실험 결과 요약

### 1. ROC-AUC 기준 최고 후보

```text
feature_set: thermal_core_plus_cyclic_event
param_set: trees_600
feature_count: 121
```

split_time_based holdout:

```text
ROC-AUC            0.7475
Average Precision 0.6625
Precision          1.0000
Recall             0.2030
F1                 0.3375
FPR                0.0000
```

기준 모델 대비:

```text
ROC-AUC +0.0323
AP      -0.0305
Recall  +0.0752
F1      +0.1108
FPR      0.0000 유지
```

해석:

- 정상/위험구간을 순위로 분리하는 능력은 개선됐다.
- threshold 0.99에서도 recall과 F1이 좋아졌다.
- 하지만 Average Precision은 하락했다.
- 따라서 score ranking 전체가 완전히 개선됐다고 보기는 어렵고, ROC-AUC 중심 후보로만 볼 수 있다.

### 2. Average Precision 기준 최고 후보

```text
feature_set: no_drift_candidates
param_set: bootstrap_true
feature_count: 190
```

split_time_based holdout:

```text
ROC-AUC            0.7202
Average Precision 0.7066
Precision          0.0000
Recall             0.0000
F1                 0.0000
FPR                0.0000
```

기준 모델 대비:

```text
ROC-AUC +0.0049
AP      +0.0137
```

해석:

- score ranking의 AP는 소폭 개선됐다.
- 그러나 0.99 threshold에서는 예측 positive가 없어 F1이 0이다.
- 이 후보는 threshold 재설정 없이는 운영 anomaly label로 쓰기 어렵다.

### 3. 0.95 threshold 기준 F1 최고 후보

```text
feature_set: thermal_core_plus_cyclic_event
param_set: default_300_auto
threshold_quantile: 0.95
```

split_time_based holdout:

```text
ROC-AUC            0.7436
Average Precision 0.6516
Precision          0.7963
Recall             0.3233
F1                 0.4599
FPR                0.0421
```

해석:

- threshold를 0.95로 낮추면 F1은 크게 오른다.
- 하지만 이것은 모델 score 자체 개선과 threshold 완화가 같이 섞인 결과다.
- 공식 운영 기준으로 바로 교체하기보다는 threshold policy 실험으로 분리해야 한다.

## Feature subset별 해석

### thermal_core_plus_cyclic_event

가장 강한 ROC-AUC 개선을 보였다.

구성:

```text
thermal / temperature / gap / heat_power / flow 계열
cyclic_time
event_context
```

의미:

- IF는 전체 195개보다 thermal 중심 subset에서 정상 패턴과 다른 구간을 더 잘 분리할 가능성이 있다.
- sensor 절대값 전체보다 thermal relation/gap 중심 신호가 anomaly score에는 더 유리할 수 있다.

### no_drift_candidates

Average Precision은 소폭 개선됐다.

제외한 feature:

```text
day_of_year
days_since_last_any_event
p_net_supply_temperature__mean
p_net_supply_temperature__max
network_temperature_gap__mean
```

의미:

- risk 쪽 drift 의심 feature를 IF에서도 제외하면 AP가 조금 올라갈 수 있다.
- 다만 threshold 0.99에서 anomaly label이 거의 나오지 않는 조합이 있어, threshold 재검토가 필요하다.

### contract_195_full + max_samples_512

195개 feature contract 전체를 유지하면서 hyperparameter만 바꾼 후보 중 가장 나았다.

```text
ROC-AUC            0.7203
Average Precision 0.6788
Recall             0.1579
F1                 0.2727
FPR                0.0000
```

기준 대비:

```text
ROC-AUC +0.0051
AP      -0.0141
F1      +0.0461
```

의미:

- 195개 전체를 그대로 쓰는 조건에서는 큰 개선은 없다.
- 단순 hyperparameter tuning만으로는 IF 성능 개선 폭이 제한적이다.

## split_substation_based holdout 결과

substation holdout에서는 개선폭이 작다.

상위 후보:

```text
sensor_cyclic_onehot + max_samples_512
ROC-AUC 0.5841
AP      0.3759
```

기준 05 substation holdout이 낮았던 점을 고려하면 약간 개선은 있지만, 여전히 약하다.

해석:

- IF는 시간 holdout에서는 thermal subset으로 개선 여지가 있다.
- 그러나 설비실 holdout 일반화는 여전히 어렵다.
- group/substation drift가 IF에서도 존재한다.

## 최종 판단

### 바로 공식 교체 여부

```text
공식 05 Isolation Forest 교체: 보류
```

이유:

- ROC-AUC 최고 후보는 AP가 하락한다.
- AP 최고 후보는 threshold 0.99에서 F1이 0이다.
- 195개 전체 + hyperparameter만으로는 개선폭이 작다.
- substation holdout 일반화는 아직 약하다.

### 의미 있는 개선 후보

다음 후보는 추가 검토 가치가 있다.

```text
thermal_core_plus_cyclic_event + trees_600
```

장점:

```text
ROC-AUC 0.7152 -> 0.7475
F1     0.2267 -> 0.3375
Recall 0.1278 -> 0.2030
FPR    0.0000 유지
```

단점:

```text
Average Precision 0.6930 -> 0.6625
```

따라서 이 후보는 공식 교체보다는 아래 용도로 먼저 쓰는 것이 맞다.

```text
1. risk 모델의 추가 anomaly feature 후보
2. thermal-only anomaly_score 보조 feature
3. Priority Engine anomaly component 보조 신호
```

## 다음 작업 제안

### 1. IF dual-score 구조 검토

공식 anomaly score를 바로 교체하지 말고, 아래처럼 두 score를 비교한다.

```text
anomaly_score_full_195
anomaly_score_thermal_context
```

이후 risk 모델에 둘 다 넣어서 downstream F1/recall/FPR을 비교한다.

### 2. thermal anomaly score를 risk feature로 추가 실험

현재 risk false negative가 thermal/event contribution에서 갈린다.
따라서 thermal IF score를 추가 feature로 넣는 실험이 가장 현실적이다.

실험 방향:

```text
risk base features
+ official anomaly_score
+ thermal_iforest_anomaly_score
+ thermal_iforest_anomaly_rank_by_group
```

### 3. substation holdout 보강

IF 자체만 튜닝해서 substation holdout을 크게 올리기는 어렵다.
제조사/구성별 normal baseline 또는 group-normalized anomaly score가 필요하다.

## 한 줄 결론

Isolation Forest는 건드릴 수 있고, thermal 중심 subset에서 ROC-AUC는 개선됐다.
하지만 AP와 substation 일반화까지 동시에 좋아진 것은 아니므로 공식 05 교체는 보류한다.
다음 단계는 thermal IF score를 risk/priority 보조 feature로 연결해 downstream 성능 개선 여부를 보는 것이다.

