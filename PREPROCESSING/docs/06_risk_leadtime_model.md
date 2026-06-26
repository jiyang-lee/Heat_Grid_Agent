# 06. LightGBM 위험도 및 리드타임 모델

이 문서는 `PREPROCESSING/hsj/06_risk_leadtime_model.ipynb`의 목적, 모델 구조, 학습 기준, 산출물, 성능 판단 기준을 정리한다.

## 1. 진행 방향

`ML_NOTEBOOK_PLAN.md`의 큰 흐름은 유지한다. 즉 `06`은 위험도와 리드타임을 함께 다룬다. 다만 모델 성능과 해석 가능성을 높이기 위해 노트북 내부 책임을 다음처럼 분리한다.

```text
06-A: LightGBM 위험도 이진 분류
06-B: LightGBM 리드타임 3중분류
06-C: 위험도 + 리드타임 + anomaly 결과 결합
```

이 방식은 plan 파일을 깨지 않으면서도 모델이 푸는 문제를 명확히 나누기 위한 절충안이다.

위험도 모델은 “이 window가 고장 신고 전 위험 패턴과 유사한가”를 먼저 판단한다. 리드타임 모델은 `pre_fault` 구간 안에서 “얼마나 임박했는가”를 3개 구간으로 분류한다.

## 2. ML 문서 기준 반영

`docs` 폴더의 `ML_` 문서들을 다시 확인했고, 06에는 다음 기준을 반영한다.

`ML_HANDOFF.md` 기준:

- ML은 최종 우선순위를 직접 정하지 않는다.
- ML은 Agent가 판단할 수 있도록 `anomaly_score`, `risk_probability`, `lead_time_bucket`, 근거 정보를 제공한다.
- 기본 모델 체인은 `Isolation Forest + LightGBM` 구조를 따른다.

`ML_OUTPUT_CONTRACT.md` 기준:

- Agent가 읽을 수 있는 핵심 필드는 `substation_id`, `window_start`, `window_end`, `anomaly_score`, `risk_probability`, `risk_class`, `risk_level`, `lead_time_bucket`, `lead_time_confidence`, `model_version`이다.
- ML 결과는 점수 묶음이며, 최종 priority나 작업 지시는 Agent가 만든다.
- 각 결과에는 재현 가능한 metadata와 model version을 남긴다.

`ML_PAPER_GUIDELINE.md` 기준:

- 단순 정확도만 보지 않고 reliability와 earliness를 함께 본다.
- 정상 이벤트에서 false alarm이 너무 많으면 운영자가 무시하게 되므로 false positive를 관리한다.
- fault event에서는 얼마나 빨리 감지하는지, 즉 lead time을 함께 본다.
- 이후 07에서 feature attribution과 센서 중요도를 제공할 수 있도록 feature importance를 저장한다.

`ML_NOTEBOOK_PLAN.md` 기준:

- 06은 위험도 및 리드타임 추정 단계다.
- 07은 근거 설명 및 센서 중요도 단계다.
- 08은 Agent 전달용 export 단계다.
- 현재 작업 경로는 04부터 `hsj`로 진행 중이므로 실제 파일은 `PREPROCESSING/hsj/06_risk_leadtime_model.ipynb`에 둔다.

## 3. 입력 데이터

06은 04와 05 산출물을 입력으로 사용한다.

```text
data/processed/ml_features/trainable_windows.csv
data/processed/ml_features/feature_columns.csv
data/processed/ml_baseline/anomaly_baseline_scores.csv
```

`trainable_windows.csv`는 03 window와 04 feature selection 결과를 기반으로 만든 학습 가능 테이블이다.

`feature_columns.csv`는 모델별 feature 사용 여부를 담는다.

`anomaly_baseline_scores.csv`는 05 Isolation Forest 결과이며, 06에서는 `anomaly_score`, `anomaly_label`, `anomaly_threshold`를 결합한다.

## 4. 현재 라벨 구조

현재 로컬 산출물 기준 `trainable_windows.csv`는 3270개 window를 가진다.

time-based split에서 supervised 학습 가능 샘플은 다음과 같다.

```text
train normal: 1252
train pre_fault: 456
validation normal: 268
validation pre_fault: 109
holdout normal: 257
holdout pre_fault: 121
```

리드타임 학습 대상은 `pre_fault` 중 `estimated_lead_time_hours`가 있는 row다.

현재 3중분류 bucket은 다음처럼 정의한다.

```text
short_0_24h: 0시간 초과 24시간 이하
mid_24_72h: 24시간 초과 72시간 이하
long_72h_plus: 72시간 초과
```

현재 전체 리드타임 bucket 분포는 다음과 같다.

```text
short_0_24h: 224
mid_24_72h: 388
long_72h_plus: 74
```

이 기준을 선택한 이유는 운영 해석이 쉽기 때문이다. `24시간 이내`는 긴급 확인 후보, `24~72시간`은 단기 추적 후보, `72시간 초과`는 중기 관찰 후보로 Agent가 해석할 수 있다.

## 5. Feature 사용 원칙

위험도 모델은 `feature_columns.csv`에서 `risk_feature == True`인 컬럼을 기본 feature로 사용한다. 여기에 05 결과인 `anomaly_score`, `anomaly_label`을 추가한다.

리드타임 모델은 `feature_columns.csv`에서 `leadtime_feature == True`인 컬럼을 기본 feature로 사용한다. 마찬가지로 05 결과인 `anomaly_score`, `anomaly_label`을 추가한다.

이번 baseline에서는 리드타임 모델 학습 feature에 `risk_probability`를 넣지 않는다.

그 이유는 다음과 같다.

- `risk_probability`는 06-A 위험도 모델의 supervised 결과다.
- 같은 train set에서 만든 risk 결과를 06-B 리드타임 train feature로 바로 넣으면 label proxy처럼 작동할 수 있다.
- validation/holdout에서는 실제 추론 흐름과 비슷하지만 train 성능이 과하게 좋아질 위험이 있다.
- 따라서 첫 baseline은 04 base feature와 05 anomaly feature만 사용하고, 최종 산출물에서 두 모델 결과를 나란히 결합한다.

추후 성능 개선 단계에서는 out-of-fold risk probability를 만든 뒤 리드타임 feature로 넣는 stacking 방식을 검토할 수 있다.

## 6. 위험도 모델

위험도 모델은 LightGBM 이진 분류 모델이다.

Target은 다음과 같이 만든다.

```text
label == pre_fault -> risk_target 1
label == normal -> risk_target 0
```

`unlabeled`는 score 산출 대상에는 남길 수 있지만 supervised 학습/평가에는 사용하지 않는다.

모델 후보는 다음 hyperparameter grid를 비교한다.

```text
n_estimators: 300, 600
learning_rate: 0.03, 0.05
num_leaves: 15, 31
min_child_samples: 20, 50
```

Threshold 후보는 다음처럼 둔다.

```text
0.20, 0.25, 0.30, ..., 0.80
```

위험도 모델 선택 기준은 다음 순서다.

```text
validation f1
낮은 validation false_positive_rate
validation precision
validation recall
validation average_precision
validation roc_auc
```

이 기준은 현재 사용자 의사결정과 맞춘 것이다. 이상 또는 위험 탐지도 중요하지만, 실제 Agent 운영에서는 불필요한 현장 확인을 줄여야 하므로 false positive를 2차 기준으로 둔다.

## 7. 리드타임 모델

리드타임 모델은 LightGBM 3중분류 모델이다.

학습 대상은 다음 조건을 만족하는 row다.

```text
use_for_supervised_training == True
label == pre_fault
estimated_lead_time_hours not null
```

리드타임 모델 후보는 다음 hyperparameter grid를 비교한다.

```text
n_estimators: 300, 600
learning_rate: 0.03, 0.05
num_leaves: 15, 31
min_child_samples: 10, 30
```

리드타임 모델 선택 기준은 다음 순서다.

```text
validation macro_f1
validation weighted_f1
validation macro_recall
validation accuracy
```

`macro_f1`을 1차 기준으로 둔 이유는 `long_72h_plus` 클래스가 상대적으로 적기 때문이다. accuracy나 weighted f1만 보면 큰 클래스인 `mid_24_72h`에 치우친 모델이 선택될 수 있다.

## 8. 산출물

06은 최신본과 run별 파일을 모두 저장한다.

최신본 경로:

```text
data/processed/ml_supervised/risk_experiment_results.csv
data/processed/ml_supervised/leadtime_experiment_results.csv
data/processed/ml_supervised/risk_leadtime_model_metrics.csv
data/processed/ml_supervised/risk_predictions.csv
data/processed/ml_supervised/leadtime_predictions.csv
data/processed/ml_supervised/agent_model_outputs.csv
data/processed/ml_supervised/risk_leadtime_feature_importance.csv
data/processed/ml_supervised/risk_leadtime_model_metadata.json
data/processed/ml_supervised/supervised_run_history.csv
data/processed/ml_supervised/supervised_run_history_plot.png
```

run별 경로:

```text
data/processed/ml_supervised/runs/run_YYYYMMDD_HHMMSS/
```

모델 파일:

```text
data/processed/ml_supervised/risk_lgbm_pipeline.joblib
data/processed/ml_supervised/leadtime_lgbm_pipeline.joblib
data/processed/ml_supervised/runs/run_YYYYMMDD_HHMMSS/models/risk_lgbm_pipeline.joblib
data/processed/ml_supervised/runs/run_YYYYMMDD_HHMMSS/models/leadtime_lgbm_pipeline.joblib
```

`data/processed/`는 `.gitignore` 대상이므로 산출물은 Git에 올리지 않고 재생성 가능한 로컬 결과로 둔다.

## 9. Agent 전달 전 결합 테이블

`agent_model_outputs.csv`는 08 export의 입력 후보로 사용한다.

핵심 컬럼은 다음과 같다.

```text
manufacturer
substation_id
source_file
window_start
window_end
label
fault_label
fault_event_id
estimated_lead_time_hours
split_time_based
configuration_type
season_bucket
anomaly_score
anomaly_threshold
anomaly_label
risk_probability
risk_score
risk_threshold
risk_class
risk_level
lead_time_bucket
lead_time_confidence
leadtime_prob_short_0_24h
leadtime_prob_mid_24_72h
leadtime_prob_long_72h_plus
risk_model_version
leadtime_model_version
run_id
```

이 테이블은 Agent가 바로 최종 판단을 내리기 위한 최종 JSON은 아니다. 08에서 계약 스키마에 맞게 요약/상세 export를 분리한다.

## 10. 성능 해석 기준

위험도 모델은 다음 순서로 본다.

1. validation f1이 이전 run보다 좋아졌는지 확인한다.
2. false positive rate가 지나치게 높지 않은지 확인한다.
3. precision과 recall 균형을 본다.
4. holdout에서도 validation과 같은 방향이 유지되는지 확인한다.
5. average precision과 roc auc가 크게 무너지지 않는지 확인한다.

리드타임 모델은 다음 순서로 본다.

1. macro f1이 어느 정도 나오는지 확인한다.
2. minority class인 `long_72h_plus`가 완전히 무시되지 않는지 확인한다.
3. weighted f1과 accuracy가 macro f1보다 지나치게 높으면 클래스 불균형 영향을 의심한다.
4. holdout에서도 bucket별 recall이 유지되는지 확인한다.

## 11. 성능 개선 후보

06 실행 후 성능이 부족하면 다음 순서로 개선한다.

1. 위험도 threshold를 운영 목적별로 나눈다. 예를 들어 `f1 최대`, `false positive 10% 이하`, `precision 우선` 기준을 별도로 비교한다.
2. 리드타임 bucket 경계를 재검토한다. 현재는 `24h`, `72h` 기준이지만 데이터 분포 기준 quantile bucket도 비교할 수 있다.
3. `split_regime_based` 기준 평가를 추가해 계절/운영 regime 변화에 강한지 본다.
4. LightGBM feature importance에서 상위 feature가 leakage에 가까운지 확인한다.
5. out-of-fold 방식으로 `risk_probability`를 만들고 리드타임 모델 feature로 추가한다.
6. false positive가 특정 manufacturer/configuration에 몰리는지 확인한다.
7. 07에서 SHAP 또는 permutation importance를 추가해 Agent가 사용할 수 있는 센서 근거를 만든다.

## 12. 다음 단계

06을 실행한 뒤 먼저 `risk_leadtime_model_metrics.csv`와 `supervised_run_history.csv`를 확인한다.

그다음 판단은 다음과 같이 한다.

```text
위험도 모델 f1과 false positive가 납득 가능하다 -> 07 근거 설명으로 이동
위험도 모델 false positive가 높다 -> threshold 또는 feature set 조정
리드타임 macro_f1이 낮다 -> bucket 경계 또는 class_weight/feature set 조정
holdout 성능이 validation보다 크게 낮다 -> split/regime shift 진단
```

06의 목적은 최종 완성 모델을 한 번에 만드는 것이 아니라, Agent에 넘길 수 있는 위험도와 리드타임 baseline을 재현 가능하게 만드는 것이다.

## 13. 2026-06-26 첫 실행 결과

06 노트북을 실행했고, 산출물은 정상적으로 생성되었다.

이번 실행 run id는 다음과 같다.

```text
run_id: run_20260626_154214
```

run별 산출물은 아래 폴더에 저장되었다.

```text
data/processed/ml_supervised/runs/run_20260626_154214/
```

동시에 다음 노트북이 읽기 쉽도록 최신본 파일도 `data/processed/ml_supervised/` 바로 아래에 저장되었다.

생성 확인된 주요 파일은 다음과 같다.

```text
data/processed/ml_supervised/runs/run_20260626_154214/risk_experiment_results.csv
data/processed/ml_supervised/runs/run_20260626_154214/leadtime_experiment_results.csv
data/processed/ml_supervised/runs/run_20260626_154214/risk_leadtime_model_metrics.csv
data/processed/ml_supervised/runs/run_20260626_154214/risk_predictions.csv
data/processed/ml_supervised/runs/run_20260626_154214/leadtime_predictions.csv
data/processed/ml_supervised/runs/run_20260626_154214/agent_model_outputs.csv
data/processed/ml_supervised/runs/run_20260626_154214/risk_leadtime_feature_importance.csv
data/processed/ml_supervised/runs/run_20260626_154214/risk_leadtime_model_metadata.json
data/processed/ml_supervised/runs/run_20260626_154214/models/risk_lgbm_pipeline.joblib
data/processed/ml_supervised/runs/run_20260626_154214/models/leadtime_lgbm_pipeline.joblib
data/processed/ml_supervised/runs/run_20260626_154214/plots/supervised_run_history_plot.png
```

## 14. 위험도 모델 실행 결과

선택된 위험도 모델 설정은 다음과 같다.

```text
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
true_negative: 251
false_positive: 17
false_negative: 60
true_positive: 49
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
true_negative: 164
false_positive: 93
false_negative: 78
true_positive: 43
```

위험도 모델은 validation 기준으로는 꽤 안정적인 출발점이다. 특히 false positive rate가 약 6.3%라서 운영 알림 부담을 크게 늘리지 않으면서 precision 0.7424를 확보했다.

다만 holdout에서는 성능이 크게 떨어졌다. holdout false positive rate가 약 36.2%까지 올라가고 precision도 0.3162로 낮아졌다. 이는 시간 또는 운영 regime이 바뀌었을 때 위험도 모델이 정상 window를 위험으로 과하게 판단할 수 있다는 뜻이다.

따라서 현재 판단은 다음과 같다.

```text
validation 기준 baseline: 성공
holdout 일반화: 추가 개선 필요
가장 큰 문제: holdout false positive 증가
```

다음 06 개선을 한다면 threshold를 더 높여 holdout false positive를 줄이는 실험과, `split_regime_based` 기준 평가를 추가하는 실험이 우선이다.

## 15. 리드타임 모델 실행 결과

선택된 리드타임 모델 설정은 다음과 같다.

```text
model_key: n_estimators=300|learning_rate=0.03|num_leaves=31|min_child_samples=30
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

리드타임 모델은 첫 baseline으로는 작동하지만 아직 강한 모델이라고 보기는 어렵다. holdout이 validation보다 좋아 보이지만, macro_f1이 0.4 미만이라 bucket별 안정성은 더 확인해야 한다.

예측 분포를 보면 `long_72h_plus` 클래스를 거의 맞히지 못하고 `short_0_24h` 또는 `mid_24_72h`로 당겨 예측하는 경향이 있다.

validation의 실제/예측 분포는 다음과 같다.

```text
actual long_72h_plus -> pred mid_24_72h: 6
actual long_72h_plus -> pred short_0_24h: 11
actual mid_24_72h -> pred mid_24_72h: 40
actual mid_24_72h -> pred short_0_24h: 28
actual short_0_24h -> pred mid_24_72h: 22
actual short_0_24h -> pred short_0_24h: 18
```

holdout의 실제/예측 분포는 다음과 같다.

```text
actual long_72h_plus -> pred mid_24_72h: 3
actual long_72h_plus -> pred short_0_24h: 5
actual mid_24_72h -> pred mid_24_72h: 50
actual mid_24_72h -> pred short_0_24h: 31
actual short_0_24h -> pred mid_24_72h: 19
actual short_0_24h -> pred short_0_24h: 32
```

현재 리드타임 모델은 `long_72h_plus`를 별도 장기 위험 클래스로 구분하지 못한다. 이는 `long_72h_plus` 샘플 수가 적고, 현재 feature만으로 장기 예고 패턴이 충분히 분리되지 않기 때문일 수 있다.

따라서 현재 판단은 다음과 같다.

```text
리드타임 baseline 생성: 성공
short/mid 구분: 일부 가능
long_72h_plus 구분: 실패에 가까움
다음 목표: long class 보완 또는 bucket 정의 재검토
```

## 16. 다음 진행 판단

이번 06 실행 결과만 보면, 바로 07로 넘어갈 수는 있다. 07은 feature importance와 근거 설명을 만드는 단계이므로 현재 모델의 약점까지 함께 설명할 수 있다.

다만 모델 성능을 먼저 더 끌어올리고 싶다면 06에서 한 번 더 개선 실험을 하는 것이 좋다.

추천 우선순위는 다음과 같다.

1. 위험도 모델은 holdout false positive를 줄이는 threshold 재탐색을 먼저 한다.
2. 위험도 모델을 validation f1 최우선 기준과 holdout 안정성 기준으로 나눠 비교한다.
3. 리드타임 모델은 `long_72h_plus`를 유지할지, `24h 이하`와 `24h 초과`의 2중분류로 단순화할지 비교한다.
4. 3중분류를 유지한다면 bucket 경계를 `24h`, `72h` 고정이 아니라 데이터 quantile 기준으로 재설정해본다.
5. 이후 07에서 feature importance를 확인해 leakage성 feature나 특정 이벤트 이력 feature 의존도가 과도한지 본다.

현재 단계에서 가장 중요한 의사결정은 다음이다.

```text
운영 알림 신뢰도를 먼저 높일 것인가 -> 06 위험도 threshold/holdout 안정성 개선
전체 파이프라인 흐름을 먼저 완성할 것인가 -> 07 근거 설명 및 센서 중요도로 이동
```
