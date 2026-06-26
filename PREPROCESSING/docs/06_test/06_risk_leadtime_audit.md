# 06-A. legacy LightGBM failure audit 문서

이 문서는 `PREPROCESSING/osj/experiments/06_test/06_risk_leadtime_audit.ipynb`의 목적과 산출물을 정리한다.

현재 이 문서는 메인 `Isolation Forest + LightGBM` 06 체인의 holdout 실패 원인과 보강 포인트를 보는 audit 문서다.

## 목적

06 audit은 새 모델을 학습하는 단계가 아니다. 기존 LightGBM 결과를 기준으로 holdout 붕괴 원인이 threshold 문제인지, split/normal 기준 문제인지, 특정 제조사/설비 구성의 분포 차이인지 분리해서 확인하는 legacy failure analysis notebook이다.

핵심 질문은 다음과 같다.

- holdout normal이 왜 높은 `risk_probability`를 받는가
- false positive가 특정 제조사, configuration type, substation에 몰리는가
- holdout normal 분포가 train normal과 얼마나 다른가
- `manufacturer 2 / SH`의 holdout normal과 pre_fault가 왜 뒤집혀 보이는가
- 어떤 그룹/분포에서 06 체인이 아직 약한지

## 입력

```text
data/processed/ml_risk/lgbm_risk_scores.csv
data/processed/ml_risk/models/risk_model_metadata.json
data/processed/ml_features/trainable_windows.csv
data/processed/label_alignment/fault_alignment.csv
data/processed/label_alignment/disturbance_alignment.csv
```

## 출력

```text
data/processed/ml_risk/holdout_split_label_diagnostics.csv
data/processed/ml_risk/holdout_error_diagnostics.csv
data/processed/ml_risk/holdout_feature_drift_diagnostics.csv
data/processed/ml_risk/holdout_group_calibration_diagnostics.csv
data/processed/ml_risk/holdout_group_threshold_diagnostics.csv
data/processed/ml_risk/holdout_label_time_diagnostics.csv
data/processed/ml_risk/manufacturer2_sh_label_time_diagnostics.csv
data/processed/ml_risk/manufacturer2_sh_substation_label_summary.csv
data/processed/ml_risk/lgbm_event_context_comparison.csv
data/processed/ml_risk/lgbm_event_context_ablation.csv
data/processed/ml_risk/lgbm_event_context_ablation_group_summary.csv
data/processed/ml_risk/lgbm_event_context_ablation_feature_importance.csv
```

## 현재 관찰

cyclic time + categorical one-hot + regime split 보강 후 06 LightGBM 성능은 다음과 같다.

```text
train ROC-AUC: 1.0000
validation ROC-AUC: 0.7786
holdout ROC-AUC: 0.7628

validation F1: 0.7336
holdout F1: 0.5297
holdout false positive rate: 0.2336
```

legacy v2 primary split 대비 변화:

```text
holdout ROC-AUC: 0.6162 -> 0.7628
holdout F1: 0.4943 -> 0.5297
holdout false positive rate: 0.6104 -> 0.2336
```

추가로 legacy 비교축인 `split_event_based`도 같이 저장한다.
이 축에서는 holdout ROC-AUC `0.7724`, holdout F1 `0.5131`, holdout false positive rate `0.2231`이다.

즉 현재 개선의 핵심은 단순 파라미터 튜닝이 아니라, normal을 `split_regime_based`로 나누고 시간/상태 context를 넣은 데 있다.

```text
holdout normal mean risk: 0.5368
holdout pre_fault mean risk: 0.6652
```

특히 `manufacturer 2 / SH`가 핵심 문제다.

```text
holdout normal:
  substation 11: 19 rows, mean risk 0.9270
  substation 59: 19 rows, mean risk 0.9285

holdout pre_fault:
  substation 45: 12 rows, mean risk 0.9178
```

즉 같은 `manufacturer 2 / SH`라도 holdout normal과 pre_fault가 같은 기계실에서 비교되는 것이 아니다. normal은 11, 59번 기계실이고 pre_fault는 45번 기계실의 단일 fault event다.

## label-time 진단 결론

`manufacturer 2 / SH` holdout normal은 2020년 3월 normal context다.

- substation 11 normal window: 2020-03-06 ~ 2020-03-12
- substation 59 normal window: 2020-03-07 ~ 2020-03-13
- substation 45 pre_fault window: 2020-03-06 ~ 2020-03-09

normal 두 기계실은 과거 fault/task 이후 구간이다.

- substation 11 최근 fault: 2019-12-06, normal까지 약 90일 이상 차이
- substation 59 최근 fault: 2020-01-24, normal까지 약 42일 이상 차이

따라서 지금 normal 라벨이 즉시 fault와 겹친다고 보기는 어렵다. 다만 train normal 기준과 열적 분포가 크게 다르다.

`manufacturer 2 / SH` holdout normal의 대표 drift:

- `p_net_return_temperature__mean`이 train normal보다 낮음
- `p_net_return_temperature__std`가 높음
- `s_hc1_supply_temperature_setpoint__std`가 높음
- normal reference outlier rate가 holdout normal에서 0.3214

## group calibration 진단

같은 holdout 377 rows 기준 비교:

```text
global:
  TP 71 / FP 209 / FN 39 / TN 58
  precision 0.2536
  recall 0.6455
  F1 0.3641

group_f1:
  TP 71 / FP 195 / FN 39 / TN 72
  precision 0.2669
  recall 0.6455
  F1 0.3777

group_normal_p90:
  TP 45 / FP 155 / FN 65 / TN 112
  precision 0.2250
  recall 0.4091
  F1 0.2903

group_normal_p95:
  TP 36 / FP 133 / FN 74 / TN 134
  precision 0.2130
  recall 0.3273
  F1 0.2581
```

group threshold는 false positive를 일부 줄이지만 recall 손실이 크거나 개선 폭이 작다. 현재 운영 모델로 채택하기 어렵다.

`manufacturer 2 / SH`만 따로 학습한 빠른 실험도 해법이 아니었다.

```text
manufacturer 2 / SH only holdout:
  rows 68
  ROC-AUC 0.0030
  AP 0.1013
  F1 0.2785
```

## event context ablation 판단

과거 fault/task 경과일 feature는 여전히 중요하고, 여기에 cyclic time과 categorical one-hot이 추가되면서 holdout false positive가 크게 줄었다.

따라서 판단은 다음과 같다.

- `event_days_only`를 현재 06 canonical으로 둔다.
- full context는 holdout F1이 조금 높지만 false positive rate가 더 높다.
- event days도 train 성능이 매우 높으므로 운영 확정 모델은 아니다.
- `manufacturer 2 / SH` 문제는 줄었지만 audit 대상에서 빠질 정도로 해결됐다고 보기는 이르다.
- 다음 보강은 해당 group의 normal 정의, 계절/운전상태 drift, post-fault 상태 분리, leadtime 재학습 쪽이다.

## 현재 판단

지금 문제는 단순한 threshold 조정이나 LightGBM 파라미터 문제로 보기 어렵다.

이 문서의 역할은 “왜 실패했는가”를 남기고, 06 체인의 다음 보강 우선순위를 고정하는 것이다.

우선순위는 다음과 같다.

1. `manufacturer 2 / SH` normal context가 “운영 정상”인지 “post-fault 안정화/계절 drift/라벨 공백”인지 분리한다.
2. 이 결과를 legacy failure evidence로 보존한다.
3. paper-aligned 전환 시도 자료는 `PREPROCESSING/legacy` 아래에 보존한다.

따라서 다음 단계는 07이 아니라 06 보강이다.


