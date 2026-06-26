# 07. 근거 설명 및 센서 중요도

이 문서는 `PREPROCESSING/hsj/07_explainability.ipynb`의 목적, 입력 데이터, 설명 생성 방식, 산출물을 정리한다.

## 1. 목적

07은 모델을 새로 학습하는 단계가 아니다. 05와 06에서 만든 모델 산출물을 읽고, Priority Engine과 Agent가 사용할 수 있는 decision feature 근거를 만든다.

주요 목적은 다음과 같다.

```text
1. 위험도/리드타임 모델의 주요 feature importance 정리
2. 고위험 window별 top sensor 또는 top feature 근거 생성
3. holdout에서 정상 window가 과대위험으로 평가되는 group 진단
4. 08 decision_features/export에서 사용할 evidence table 생성
```

06 재설계 결과에서 위험도 모델은 과대위험 판단을 줄였지만, 특정 group에서는 여전히 정상 window가 높은 risk 입력값을 받는 문제가 남아 있었다. 07은 이 문제가 어떤 feature 또는 group에서 발생하는지 확인하고, 이후 우선순위 회귀/스코어링 모델에 넣을 설명형 입력값을 만드는 단계다.

## 1.1 최종 목적과 07의 역할

최종 목적은 05/06 분류 모델로 직접 알림을 끝내는 것이 아니다.

최종 출력은 다음 질문에 답하는 것이다.

```text
어떤 설비를 먼저 점검해야 하는가
왜 해당 설비의 우선순위가 높은가
이상 징후의 주요 원인은 무엇인가
운영자가 어떤 조치를 취해야 하는가
현재 상태가 관찰, 주의, 경고, 긴급 중 어디에 해당하는가
```

따라서 05/06/07의 산출물은 최종 판단이 아니라 `decision_features`와 `priority_scores`를 만들기 위한 입력이다.

현재 역할은 다음처럼 정리한다.

```text
05 Isolation Forest -> anomaly_score, anomaly_label, anomaly_threshold
06 Risk LightGBM -> risk_probability, risk_level, risk_class
06 Leadtime LightGBM -> lead_time_bucket, lead_time_confidence, bucket별 확률
07 Explainability -> top_sensors, sensor_scores, evidence_details, overestimated_risk_diagnostic
08 이후 -> decision_features, priority_scores, 상태등급, 운영 권고
```

## 2. 입력 데이터

07은 06의 최신 산출물을 입력으로 사용한다.

```text
data/processed/ml_features/trainable_windows.csv
data/processed/ml_features/feature_columns.csv
data/processed/ml_supervised/agent_model_outputs.csv
data/processed/ml_supervised/risk_leadtime_feature_importance.csv
data/processed/ml_supervised/risk_group_diagnostics.csv
data/processed/ml_supervised/risk_threshold_diagnostics.csv
data/processed/ml_supervised/risk_leadtime_model_metadata.json
```

따라서 07을 실행하기 전에 04, 05, 06이 먼저 실행되어 있어야 한다.

## 3. 설명 생성 원칙

이번 07은 SHAP 기반 설명을 사용하지 않는다.

그 이유는 다음과 같다.

- 현재 단계에서는 추가 의존성을 늘리지 않고 재현 가능한 baseline 설명을 먼저 만드는 것이 우선이다.
- LightGBM 기본 feature importance만으로도 어떤 feature가 모델 판단에 많이 쓰였는지 확인할 수 있다.
- window별 국소 설명은 정상 train 분포 대비 feature 값이 얼마나 벗어났는지를 함께 보아 baseline 근거로 만들 수 있다.

따라서 이번 설명 방식은 다음 두 가지를 결합한다.

```text
전역 설명: LightGBM feature importance
window별 설명: normal train reference 대비 robust deviation
```

여기서 robust deviation은 train normal 구간의 median과 IQR을 기준으로 계산한다.

```text
robust_z = (현재값 - train_normal_median) / train_normal_IQR
```

각 feature의 evidence score는 다음처럼 만든다.

```text
evidence_score = abs(robust_z) * feature_importance_share
```

이 방식은 SHAP처럼 정확한 국소 기여도를 의미하지 않는다. 대신 “모델이 중요하게 본 feature 중, 현재 window에서 정상 기준 대비 크게 벗어난 feature”를 찾는 baseline이다.

## 4. Feature importance 해석

07은 `risk_lgbm`, `leadtime_lgbm` 각각의 feature importance를 정리한다.

저장되는 파일은 다음과 같다.

```text
feature_importance_summary.csv
top_feature_importance.csv
feature_family_importance.csv
```

`feature_importance_summary.csv`는 전체 feature importance와 rank, family, importance share를 담는다.

`top_feature_importance.csv`는 모델별 상위 feature만 빠르게 볼 수 있게 만든다.

`feature_family_importance.csv`는 feature family 단위로 중요도를 합산한다. 이를 통해 모델이 센서 통계, 시간/주기, 이벤트 이력, 모델 결과 중 어디에 크게 의존하는지 볼 수 있다.

## 5. Window별 근거 설명

`window_evidence.csv`는 08 decision_features/export의 설명 후보로 사용한다.

핵심 컬럼은 다음과 같다.

```text
manufacturer
substation_id
source_file
window_start
window_end
label
split_time_based
configuration_type
season_bucket
anomaly_score
anomaly_label
risk_probability
risk_class
risk_level
lead_time_bucket
lead_time_confidence
top_sensors
sensor_scores
evidence_details
pattern_notes
source_model_run_id
explainability_run_id
```

`top_sensors`는 실제 센서 이름만 담는 것은 아니다. 현재 feature engineering 결과가 window 통계 feature이므로 `network_temperature_gap__mean`, `anomaly_score`, `days_since_last_any_event`처럼 모델 입력 feature 이름이 들어갈 수 있다.

08에서 decision feature와 Agent용 문구를 만들 때는 이 이름을 더 사용자 친화적인 설명으로 바꿀 수 있다.

## 6. 과대위험 group 진단

06 재설계 run 기준으로 holdout 정상 window가 risk threshold를 넘어 과대위험으로 평가된 그룹은 다음 파일에서 정리한다.

```text
false_positive_group_diagnostics.csv
```

이 파일은 다음 질문에 답하기 위한 자료다.

```text
1. 특정 manufacturer에서 정상 window 과대위험이 몰리는가?
2. 특정 configuration에서 정상 window를 위험으로 오해하는가?
3. 계절 또는 regime에 따라 threshold가 달라져야 하는가?
4. 08 decision_features 또는 Priority Engine 단계에서 group별 보정 규칙이 필요한가?
```

06 결과 기준으로 특히 주의해야 할 그룹은 다음이었다.

```text
holdout manufacturer 2
holdout configuration_type SH + DHW
holdout season_bucket spring
holdout split_regime_based train
```

07은 이 그룹들을 우선 진단 대상으로 정리한다.

## 7. 산출물

07은 최신본과 run별 파일을 모두 저장한다.

최신본 경로:

```text
data/processed/ml_explainability/feature_importance_summary.csv
data/processed/ml_explainability/top_feature_importance.csv
data/processed/ml_explainability/feature_family_importance.csv
data/processed/ml_explainability/window_evidence.csv
data/processed/ml_explainability/false_positive_group_diagnostics.csv
data/processed/ml_explainability/explainability_metadata.json
data/processed/ml_explainability/risk_lgbm_top_feature_importance.png
data/processed/ml_explainability/leadtime_lgbm_top_feature_importance.png
```

run별 경로:

```text
data/processed/ml_explainability/runs/run_YYYYMMDD_HHMMSS/
```

`data/processed/`는 `.gitignore` 대상이므로 산출물은 Git에 올리지 않는다.

## 8. 현재 방식의 한계

이번 07은 baseline explainability다.

한계는 다음과 같다.

- LightGBM feature importance는 모델 전체에서 자주 사용된 feature를 보여줄 뿐, 개별 window에서 실제로 어떤 방향으로 영향을 줬는지까지 정확히 말하지 않는다.
- robust deviation은 정상 기준 대비 벗어난 정도를 보여주지만, 그 feature가 risk probability를 올렸는지 내렸는지는 직접 증명하지 않는다.
- `top_sensors`에는 센서 원천 컬럼이 아니라 window 통계 feature가 들어간다.

따라서 이후 설명 품질을 높이려면 다음을 검토한다.

```text
1. SHAP 기반 국소 설명 추가
2. window 통계 feature를 원천 센서명으로 mapping
3. feature family별 설명 문구 개선
4. 과대위험 group별 threshold 또는 priority 보정 규칙 설계
```

## 9. 다음 단계

07 실행 후에는 다음을 확인한다.

```text
1. risk_lgbm 상위 feature가 이벤트 이력에 과도하게 의존하는지
2. anomaly_score가 위험도 판단에 어느 정도 기여하는지
3. 과대위험 group에서 공통적으로 튀는 feature가 있는지
4. 08 decision_features/export에 넣을 top_sensors와 pattern_notes가 충분히 읽을 만한지
```

확인 후 바로 08 decision_features/export로 넘어갈 수 있다. 다만 설명 결과에서 leakage성 feature 의존이 과도하거나 특정 group 과대위험 원인이 분명하면, 06 feature set 또는 threshold를 다시 조정하는 것이 좋다.

## 10. 2026-06-26 첫 실행 결과

07 노트북을 실행했고, explainability 산출물이 정상적으로 생성되었다.

이번 실행 run id는 다음과 같다.

```text
run_id: run_20260626_162553
source_model_run_id: run_20260626_155956
```

run별 산출물은 아래 폴더에 저장되었다.

```text
data/processed/ml_explainability/runs/run_20260626_162553/
```

생성 확인된 주요 파일은 다음과 같다.

```text
data/processed/ml_explainability/feature_importance_summary.csv
data/processed/ml_explainability/top_feature_importance.csv
data/processed/ml_explainability/feature_family_importance.csv
data/processed/ml_explainability/window_evidence.csv
data/processed/ml_explainability/false_positive_group_diagnostics.csv
data/processed/ml_explainability/explainability_metadata.json
data/processed/ml_explainability/risk_lgbm_top_feature_importance.png
data/processed/ml_explainability/leadtime_lgbm_top_feature_importance.png
```

## 11. Risk 모델 중요 feature

`risk_lgbm`의 상위 feature는 다음과 같다.

```text
1. days_since_last_any_event
2. day_of_year
3. anomaly_score
4. doy_cos
5. days_since_last_fault_event
6. doy_sin
7. network_temperature_gap__mean
8. s_dhw_lower_storage_temperature__min
9. p_net_return_temperature__max
10. p_hc1_return_temperature__min
```

해석하면 risk 모델은 센서 통계만 보는 것이 아니라 이벤트 이력, 계절/연중 주기, Isolation Forest anomaly score를 함께 사용하고 있다.

family 단위 중요도는 다음과 같다.

```text
센서 통계: 62.3%
시간/주기: 16.4%
이벤트 이력: 15.4%
모델결과/기타: 5.9%
```

이 결과는 긍정적인 면과 주의할 점이 함께 있다.

긍정적인 점은 센서 통계가 가장 큰 비중을 차지하므로 모델이 실제 운전 상태를 상당히 반영한다는 것이다. 또한 `anomaly_score`가 3위에 있어 05 Isolation Forest 결과가 06 risk 모델에서 의미 있게 사용되고 있다.

주의할 점은 `days_since_last_any_event`, `days_since_last_fault_event`, `day_of_year`, `doy_cos`, `doy_sin`처럼 이벤트 이력과 시간 feature가 상위권에 있다는 것이다. 이 feature들은 실제 운영 패턴을 잘 반영할 수 있지만, 특정 기간이나 이벤트 패턴에 과적합하면 holdout에서 false positive를 만들 수 있다.

## 12. Leadtime 모델 중요 feature

`leadtime_lgbm`의 상위 feature는 다음과 같다.

```text
1. doy_sin
2. days_since_last_any_event
3. outdoor_temperature__std
4. dow_sin
5. s_hc1_supply_temperature__std
6. p_net_meter_flow__mean
7. outdoor_temperature__max
8. outdoor_temperature__first
9. p_net_meter_flow__min
10. p_net_supply_temperature__std
```

family 단위 중요도는 다음과 같다.

```text
센서 통계: 80.0%
시간/주기: 13.1%
이벤트 이력: 5.7%
모델결과/기타: 1.2%
```

리드타임 모델은 risk 모델보다 센서 통계 의존도가 훨씬 크다. 이는 3중분류 리드타임 모델이 이벤트 이력보다 온도, 유량, 열량계, 계절성 변동을 더 많이 사용한다는 뜻이다.

다만 `doy_sin`이 1위이고 `dow_sin`도 상위권에 있으므로 리드타임 분류가 계절/요일 패턴을 함께 강하게 보고 있다. 이 자체는 district heating 데이터 특성상 자연스럽지만, 실제 고장 임박성보다 계절적 분포 차이를 학습했는지는 추가 확인이 필요하다.

## 13. False positive group 진단 결과

07에서 정리한 holdout 과대위험 주요 그룹은 다음과 같다.

```text
split_regime_based = train
false_positive_rate: 0.4737
false_positive: 27
true_positive: 0
rows: 100

manufacturer = manufacturer 2
false_positive_rate: 0.2069
false_positive: 30
true_positive: 0
rows: 186

configuration_type = SH + DHW
false_positive_rate: 0.1629
false_positive: 29
true_positive: 20
rows: 252

season_bucket = spring
false_positive_rate: 0.1429
false_positive: 30
true_positive: 0
rows: 281
```

가장 중요한 신호는 `manufacturer 2`와 `spring`에서 정상 window 과대위험 건수는 많은데 true positive가 0이라는 점이다. 이 경우 모델이 실제 pre_fault를 잡았다기보다 해당 그룹의 정상 패턴을 위험 신호로 오해했을 가능성이 있다.

`configuration_type = SH + DHW`는 과대위험도 있지만 true positive도 20건이 있으므로, 단순히 버릴 그룹은 아니다. 이 그룹에서는 threshold, decision feature 보정 또는 evidence 설명을 더 정교하게 만들어야 한다.

## 14. Window evidence 결과

`window_evidence.csv`는 총 500개 window에 대해 생성되었다.

구성은 다음과 같다.

```text
risk_level high: 500
label pre_fault: 430
label unlabeled: 70
split train: 484
split validation: 12
split holdout: 4
```

현재 evidence table은 risk probability가 높은 window를 우선 정렬했기 때문에 대부분 train의 high risk pre_fault가 포함되었다. 이는 “모델이 어떤 패턴을 고위험으로 보는지”를 설명하는 데는 유용하지만, holdout 과대위험 원인을 분석하기에는 holdout 샘플이 너무 적다.

예시 evidence에서는 다음 feature들이 자주 등장했다.

```text
days_since_last_any_event
day_of_year
days_since_last_fault_event
doy_sin
anomaly_score
p_net_meter_flow__min
p_net_meter_flow__mean
p_net_meter_heat_power__mean
```

특히 manufacturer 2의 고위험 window에서는 유량과 열량계 관련 feature가 정상 기준 대비 크게 튀는 사례가 보였다. 이 부분은 실제 센서 단위 설명으로 발전시키기 좋은 후보지만, 값 스케일이 매우 크게 튀는 row가 있어 원천 데이터 단위 또는 meter feature scaling 문제도 함께 확인해야 한다.

## 15. 현재 07 결과의 판단

이번 07은 baseline explainability 산출물 생성에는 성공했다.

성공한 부분은 다음과 같다.

```text
1. risk/leadtime 모델별 상위 feature를 정리했다.
2. feature family 단위 중요도까지 확인했다.
3. 과대위험이 몰리는 group을 정리했다.
4. 08 decision_features/export에 넘길 수 있는 window_evidence.csv를 만들었다.
```

하지만 바로 08로 넘어가기 전에 07을 한 번 더 가볍게 보완하면 좋다.

현재 가장 큰 한계는 `window_evidence.csv`가 고위험 train window 중심이라는 점이다. priority 입력 근거에는 필요하지만, 지금 우리가 궁금한 “holdout 정상 window가 왜 높은 우선순위 입력값을 받을 수 있는가”를 보기에는 부족하다.

따라서 다음 보완 후보는 다음과 같다.

```text
1. holdout 과대위험 window만 따로 뽑은 false_positive_window_evidence.csv 생성
2. high risk뿐 아니라 medium risk도 일부 포함해 설명 범위 확대
3. top_sensors를 원천 센서명에 가깝게 정리하는 mapping 추가
4. p_net_meter_flow, p_net_meter_heat_power처럼 스케일이 크게 튀는 feature의 원천값 점검
```

## 16. 다음 단계 제안

추천 방향은 두 가지다.

첫 번째는 07을 한 번 더 보완하는 것이다. 지금 모델의 가장 큰 우선순위 입력 리스크가 holdout 정상 window의 과대위험 평가이므로, `false_positive_window_evidence.csv`를 별도로 만들어 어떤 feature가 과대위험 window에서 반복적으로 튀는지 확인하는 편이 좋다.

두 번째는 바로 08 decision_features/export로 넘어가는 것이다. 08에서는 현재 `agent_model_outputs.csv`와 `window_evidence.csv`를 결합해 Priority Engine과 Agent 전달용 JSON/CSV를 만들 수 있다.

내 추천은 다음과 같다.

```text
07 보완 1회 -> 커밋 -> 08 decision_features/export 진행
```

이유는 07 보완이 크지 않고, 이후 08의 품질을 바로 높여주기 때문이다. 특히 08에서 Priority Engine이 “이 설비는 과대위험 가능성이 높은 group에 속한다”는 보정 신호를 함께 받을 수 있게 만들려면, 07에서 과대위험 window evidence를 분리해두는 것이 좋다.

## 17. 현재까지의 모델 성능 요약

현재까지 학습 또는 평가한 모델은 모두 회귀가 아니라 분류 또는 이상탐지 기반이다. 단, 이 모델들의 최종 목적은 직접 알림을 내는 것이 아니라 이후 우선순위 회귀/스코어링 모델의 입력 신호를 만드는 것이다.

```text
05 Isolation Forest: 비지도 이상탐지 후 threshold 기반 이진 판단
06 Risk LightGBM: pre_fault 여부 이진 분류
06 Leadtime LightGBM: short/mid/long 3중분류
07 Explainability: 학습 모델 아님, 결과 해석
```

### 17.1 05 Isolation Forest 이상탐지

05의 최고 threshold 기반 f1 성능은 `run_20260626_144708` 또는 동일 결과인 `run_20260626_150028`에서 나왔다.

선택 설정은 다음과 같다.

```text
model_key: split_time_based|0.4|300|1.0|0.8
feature_count: 130
threshold_quantile: 0.8
threshold: -0.043719924842822194
```

validation 성능은 다음과 같다.

```text
average_precision: 0.4789
roc_auc: 0.6334
precision: 0.5493
recall: 0.3120
f1: 0.3980
false_positive_rate: 0.1181
```

holdout 성능은 다음과 같다.

```text
average_precision: 0.6028
roc_auc: 0.7077
precision: 0.5789
recall: 0.3929
f1: 0.4681
false_positive_rate: 0.1498
```

해석하면, Isolation Forest는 threshold를 낮춘 뒤 실제 pre_fault 탐지력은 좋아졌지만 false positive가 10% 이상으로 올라갔다. 따라서 05 결과는 단독 최종 판단보다는 06 risk 모델의 입력 신호로 사용하는 것이 적절하다.

### 17.2 06 Risk LightGBM 이진분류

Risk 모델은 두 기준을 나눠 봐야 한다.

첫 번째는 f1 중심 baseline이다.

```text
run_id: run_20260626_154214
model_key: n_estimators=300|learning_rate=0.03|num_leaves=15|min_child_samples=50
threshold: 0.8
```

validation 성능은 다음과 같다.

```text
accuracy: 0.7958
precision: 0.7424
recall: 0.4495
f1: 0.5600
average_precision: 0.5874
roc_auc: 0.5701
false_positive_rate: 0.0634
```

holdout 성능은 다음과 같다.

```text
accuracy: 0.5476
precision: 0.3162
recall: 0.3554
f1: 0.3346
average_precision: 0.3503
roc_auc: 0.5361
false_positive_rate: 0.3619
```

두 번째는 priority 입력값의 과대평가를 줄이는 안정성 중심 threshold 재설계 결과다.

```text
run_id: run_20260626_155956
model_key: n_estimators=300|learning_rate=0.03|num_leaves=31|min_child_samples=50
threshold: 0.95
threshold_strategy: validation_fp_precision_guard
```

validation 성능은 다음과 같다.

```text
accuracy: 0.8302
precision: 0.9412
recall: 0.4404
f1: 0.6000
average_precision: 0.5919
roc_auc: 0.5739
false_positive_rate: 0.0112
```

holdout 성능은 다음과 같다.

```text
accuracy: 0.6534
precision: 0.4000
recall: 0.1653
f1: 0.2339
average_precision: 0.4189
roc_auc: 0.5449
false_positive_rate: 0.1167
```

현재 priority 입력 관점에서는 `run_20260626_155956`이 더 안정적이다. 정상 설비가 과도하게 높은 priority 입력값을 받는 문제를 줄였기 때문이다. 다만 recall이 낮아졌으므로 실제 위험구간의 priority가 충분히 올라가지 않을 수 있다는 trade-off가 있다.

### 17.3 06 Leadtime LightGBM 3중분류

Leadtime 모델은 프로젝트 목적상 3중분류를 유지한다.

```text
model_key: n_estimators=300|learning_rate=0.03|num_leaves=31|min_child_samples=30
classes: short_0_24h, mid_24_72h, long_72h_plus
```

validation 성능은 다음과 같다.

```text
accuracy: 0.4862
macro_f1: 0.3400
weighted_f1: 0.4576
macro_precision: 0.3195
macro_recall: 0.3771
```

holdout 성능은 다음과 같다.

```text
accuracy: 0.5785
macro_f1: 0.3968
weighted_f1: 0.5647
macro_precision: 0.3919
macro_recall: 0.4230
```

Leadtime 모델은 baseline으로는 작동하지만 아직 강한 모델은 아니다. 특히 `long_72h_plus` 구분이 약하므로, 이후에는 3중분류 구조를 유지하되 bucket 경계 또는 feature set을 재검토할 필요가 있다.

## 18. 07 보완 내용

07 보완에서는 holdout 정상 window 중 risk threshold를 넘은 과대위험 window를 별도 산출물로 분리한다.

새로 추가한 산출물은 다음과 같다.

```text
data/processed/ml_explainability/false_positive_window_evidence.csv
data/processed/ml_explainability/false_positive_feature_summary.csv
data/processed/ml_explainability/decision_feature_evidence.csv
```

`false_positive_window_evidence.csv`는 다음 조건을 만족하는 window만 담는다.

```text
split_time_based == holdout
label == normal
risk_class == 1
```

즉 정상 holdout window인데 Risk 모델이 high risk로 분류해 priority 입력값이 과도하게 높아질 수 있는 사례다.

`false_positive_feature_summary.csv`는 과대위험 window에서 반복적으로 등장하는 evidence feature를 집계한다. 이 파일을 보면 priority 과대평가에서 어떤 feature가 자주 튀는지 확인할 수 있다.

`decision_feature_evidence.csv`는 일반 고위험 evidence와 과대위험 진단 evidence를 함께 담는다. 08에서 `decision_features`를 만들 때 이 파일을 사용하면, 우선순위 점수를 높이는 근거와 과대평가 보정 근거를 함께 넘길 수 있다.

이 보완의 목적은 다음과 같다.

```text
1. 08 decision_features에서 과대위험 가능성이 높은 group/window에 보정 정보를 붙인다.
2. 06 feature ablation에서 제거하거나 약화할 feature 후보를 찾는다.
3. 특정 group 또는 feature가 priority 과대평가를 반복적으로 만드는지 확인한다.
```

## 19. 이후 feature 개선 방향

새 feature를 바로 추가하기보다는 먼저 feature ablation을 추천한다.

현재 risk 모델은 이벤트 이력과 시간/주기 feature를 꽤 많이 사용한다. 이 feature들이 실제 위험 신호를 잘 잡는 데 도움을 줄 수도 있지만, holdout 정상 window의 priority 과대평가를 만드는 원인일 수도 있다.

따라서 다음 06 개선 실험은 아래 순서가 좋다.

```text
A. 현재 feature set 유지
B. 이벤트 이력 feature 제외
C. 시간/주기 feature 제외
D. 이벤트 이력 + 시간/주기 feature 제외
E. 센서 통계 + anomaly_score 중심 feature set
```

새 파생 feature 생성은 그 다음 단계가 좋다. 현재 문제는 feature가 부족하다기보다 어떤 feature가 priority 과대평가를 만드는지 아직 좁히는 중이기 때문이다.

## 20. 2026-06-26 decision feature 관점 재실행 결과

07을 decision feature 관점으로 수정한 뒤 다시 실행했다.

이번 실행 run id는 다음과 같다.

```text
run_id: run_20260626_172308
source_model_run_id: run_20260626_155956
```

run별 산출물은 아래 폴더에 저장되었다.

```text
data/processed/ml_explainability/runs/run_20260626_172308/
```

새로 확인한 주요 산출물은 다음과 같다.

```text
data/processed/ml_explainability/decision_feature_evidence.csv
data/processed/ml_explainability/false_positive_window_evidence.csv
data/processed/ml_explainability/false_positive_feature_summary.csv
```

`decision_feature_evidence.csv`는 총 531개 row를 가진다.

```text
일반 risk/anomaly evidence: 500개
과대위험 진단 evidence: 31개
```

`false_positive_window_evidence.csv`는 holdout 정상 window 중 risk threshold를 넘어 priority 입력에서 과대평가될 수 있는 window만 모은 파일이다. 이번 실행에서는 31개 row가 생성되었다.

과대위험 window의 그룹 분포는 다음과 같다.

```text
manufacturer 2: 31개
spring: 31개
configuration_type SH + DHW: 29개
configuration_type SH: 2개
split_regime_based train: 27개
split_regime_based validation: 3개
split_regime_based holdout: 1개
```

즉 현재 priority 과대평가 위험은 무작위로 퍼져 있다기보다 `manufacturer 2`, `spring`, `SH + DHW` 조합에 강하게 몰려 있다.

과대위험 window에서 반복적으로 등장한 feature는 다음과 같다.

```text
doy_sin: 31회, high
day_of_year: 31회, low
days_since_last_any_event: 21회, low
s_hc1_supply_temperature__std: 18회, high
s_hc1_supply_temperature_setpoint__std: 15회, high
p_net_supply_temperature__std: 12회, high
anomaly_score: 11회, high
p_net_meter_flow__mean: 10회, high
outdoor_temperature__std: 8회, high
p_net_meter_flow__min: 8회, high
network_temperature_gap__mean: 8회, low
s_dhw_upper_storage_temperature__max: 8회, low
```

이 결과는 두 가지로 해석된다.

첫째, 시간/계절 feature가 과대평가에 매우 반복적으로 등장한다. `doy_sin`, `day_of_year`가 31개 과대위험 window 전체에서 등장했다. 이 말은 risk 모델이 봄철 특정 시기 패턴을 위험 신호처럼 사용할 가능성이 있다는 뜻이다.

둘째, 실제 센서 통계도 함께 튄다. 난방 공급온도 표준편차, 난방 공급온도 setpoint 표준편차, 네트워크 공급온도 표준편차, 유량 평균/최소값, anomaly_score가 반복적으로 등장했다. 따라서 이 문제를 단순히 시간 feature만의 문제로 보기는 어렵다.

현재 판단은 다음과 같다.

```text
07 보완 산출물 생성: 성공
decision_features 입력 근거 생성: 성공
priority 과대평가 위험 그룹 식별: 성공
다음 개선 후보: 06 feature ablation 또는 08 decision_features 보정 규칙
```

## 21. 다음 진행 제안

이제 바로 08로 넘어갈 수 있다. 08에서는 `agent_model_outputs.csv`와 `decision_feature_evidence.csv`를 결합해 `decision_features` 테이블을 만들면 된다.

08에서 포함하면 좋은 decision feature는 다음과 같다.

```text
anomaly_score
anomaly_label
risk_probability
risk_level
lead_time_bucket
lead_time_confidence
leadtime bucket별 probability
top_sensors
sensor_scores
evidence_score 요약
overestimated_risk_group flag
manufacturer/configuration/season 보정 후보
priority_input_role
```

다만 08로 가기 전에 06 feature ablation을 먼저 해도 된다.

내 추천은 다음과 같다.

```text
1. 현재 07 결과를 커밋한다.
2. 08 decision_features/export를 먼저 만든다.
3. 08 결과를 본 뒤, 필요한 경우 06 feature ablation으로 돌아간다.
```

이유는 지금은 최종 목적이 priority 회귀/스코어링 모델의 입력 테이블을 만드는 것이기 때문이다. feature ablation은 중요하지만, 먼저 `decision_features` 형태를 만들어야 어떤 feature를 줄이고 어떤 보정 신호를 넣을지 더 명확해진다.
