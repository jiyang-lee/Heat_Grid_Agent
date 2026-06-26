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

## 17. 06 재설계 방향

첫 실행 이후 바로 07로 넘어가기보다 06을 한 번 더 조정한다.

이번 재설계의 핵심은 다음과 같다.

```text
위험도 모델: threshold 재탐색과 holdout 안정성 진단 강화
리드타임 모델: 프로젝트 목적에 맞게 3중분류 유지
추가 진단: manufacturer/configuration/season/regime별 false positive 확인
```

여기서 말한 holdout 약화 또는 holdout 붕괴는 모델이 완전히 실패했다는 뜻이 아니다. validation에서는 좋게 보였던 성능이 holdout에서 크게 약해졌다는 뜻이다.

첫 실행의 위험도 모델은 validation에서 false positive rate가 약 `6.3%`였지만, holdout에서는 약 `36.2%`까지 올라갔다. 즉 검증 구간에서는 정상 window를 대체로 정상으로 보았지만, holdout 구간에서는 정상 window도 위험으로 많이 판단했다.

이 현상은 다음 가능성을 뜻한다.

```text
1. 시간에 따라 데이터 분포가 바뀌었을 수 있다.
2. 계절 또는 운영 regime이 train/validation과 holdout에서 다를 수 있다.
3. 특정 manufacturer 또는 configuration에서 false positive가 몰렸을 수 있다.
4. 현재 threshold 0.8이 validation에는 적합하지만 holdout에는 너무 낮을 수 있다.
```

따라서 이번 재설계에서는 holdout을 직접 학습 기준으로 쓰지는 않는다. holdout을 기준으로 모델을 고르면 최종 시험지를 보고 답을 고르는 것과 비슷해져서 평가가 오염될 수 있기 때문이다.

대신 validation 기준으로 더 보수적인 운영형 threshold를 고르고, holdout에서는 그 선택이 얼마나 버티는지 진단한다.

## 18. 위험도 threshold 재탐색 변경사항

기존 threshold 후보는 다음과 같았다.

```text
0.20, 0.25, 0.30, ..., 0.80
```

재설계 후 threshold 후보는 다음처럼 더 촘촘하고 높은 구간까지 확장한다.

```text
0.20, 0.225, 0.25, ..., 0.95
```

위험도 모델 선택은 먼저 validation에서 다음 조건을 만족하는 후보를 찾는다.

```text
validation false_positive_rate <= 0.05
validation precision >= 0.70
```

이 조건을 만족하는 후보가 있으면 그 후보들 중에서 다음 순서로 고른다.

```text
validation f1
낮은 validation false_positive_rate
validation precision
validation recall
validation average_precision
validation roc_auc
```

만약 조건을 만족하는 후보가 하나도 없으면 기존처럼 f1 우선 기준으로 fallback한다.

이렇게 바꾼 이유는 운영 관점 때문이다. 위험도 모델은 조기 탐지도 중요하지만, 현장 확인 알림이 너무 많이 울리면 Agent 결과를 사용자가 신뢰하기 어렵다. 따라서 첫 baseline보다 false positive를 조금 더 강하게 억제하는 방향으로 threshold를 고른다.

이번 재설계 노트북은 다음 추가 산출물을 저장한다.

```text
data/processed/ml_supervised/risk_selected_candidate_pool.csv
data/processed/ml_supervised/risk_threshold_diagnostics.csv
data/processed/ml_supervised/risk_group_diagnostics.csv
```

`risk_threshold_diagnostics.csv`는 선택된 위험도 모델에서 threshold별 validation/holdout 성능을 모두 저장한다. 이 파일을 보면 threshold를 높였을 때 false positive가 얼마나 줄고 recall이 얼마나 손실되는지 비교할 수 있다.

`risk_group_diagnostics.csv`는 manufacturer, configuration, season, split_regime_based별 성능을 저장한다. 이 파일은 holdout false positive가 특정 그룹에 몰리는지 확인하기 위한 진단표다.

## 19. 리드타임 3중분류 유지

리드타임 모델은 이번 재설계에서 2중분류로 바꾸지 않는다.

프로젝트 목적상 Agent가 단순히 “위험하다/위험하지 않다”만 아는 것보다, 위험이 어느 정도 시간 범위에 있는지 알아야 한다. 따라서 다음 3개 bucket을 유지한다.

```text
short_0_24h
mid_24_72h
long_72h_plus
```

다만 첫 실행에서 `long_72h_plus` 구분이 약했으므로, 다음 실행 후에도 같은 문제가 반복되면 3중분류 구조는 유지하되 bucket 경계를 재조정하는 방향을 검토한다.

예를 들어 다음 후보를 비교할 수 있다.

```text
현재 기준: 0~24h / 24~72h / 72h+
대안 1: 0~24h / 24~96h / 96h+
대안 2: 데이터 quantile 기반 3분할
대안 3: event 단위 대표 lead time 기준으로 재라벨링
```

이번 수정에서는 우선 threshold와 holdout 안정성 진단에 집중하고, 리드타임 bucket 자체는 바꾸지 않는다.

## 20. 2026-06-26 재설계 실행 결과

06 재설계 노트북을 다시 실행했고, 새 run 산출물이 정상적으로 생성되었다.

이번 실행 run id는 다음과 같다.

```text
run_id: run_20260626_155956
```

run별 산출물은 아래 폴더에 저장되었다.

```text
data/processed/ml_supervised/runs/run_20260626_155956/
```

이번 실행에서는 새로 추가한 진단 파일도 생성되었다.

```text
data/processed/ml_supervised/risk_selected_candidate_pool.csv
data/processed/ml_supervised/risk_threshold_diagnostics.csv
data/processed/ml_supervised/risk_group_diagnostics.csv
```

선택된 위험도 모델 설정은 다음과 같다.

```text
model_key: n_estimators=300|learning_rate=0.03|num_leaves=31|min_child_samples=50
threshold_strategy: validation_fp_precision_guard
threshold: 0.95
false_positive_guard: 0.05
precision_guard: 0.70
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
true_negative: 265
false_positive: 3
false_negative: 61
true_positive: 48
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
true_negative: 227
false_positive: 30
false_negative: 101
true_positive: 20
```

이전 run과 비교하면 위험도 모델은 다음처럼 바뀌었다.

```text
validation precision: 0.7424 -> 0.9412
validation recall: 0.4495 -> 0.4404
validation f1: 0.5600 -> 0.6000
validation false_positive_rate: 0.0634 -> 0.0112

holdout precision: 0.3162 -> 0.4000
holdout recall: 0.3554 -> 0.1653
holdout f1: 0.3346 -> 0.2339
holdout false_positive_rate: 0.3619 -> 0.1167
```

이번 재설계는 의도한 대로 false positive를 크게 줄였다. validation false positive는 17건에서 3건으로 줄었고, holdout false positive도 93건에서 30건으로 줄었다.

다만 trade-off가 분명하다. threshold를 `0.95`까지 높이면서 holdout recall이 0.3554에서 0.1653으로 떨어졌다. 즉 헛알림은 줄었지만, 실제 pre_fault 위험구간을 놓치는 비율이 늘었다.

현재 판단은 다음과 같다.

```text
알림 신뢰도 개선: 성공
holdout false positive 감소: 성공
위험 탐지 민감도: 악화
운영형 threshold 후보: 0.95
탐지형 threshold 후보: 이전 run의 0.8 또는 threshold diagnostics에서 중간 후보 재검토
```

따라서 지금부터는 하나의 threshold를 무조건 고르기보다 목적별 threshold를 나누어 보는 것이 좋다.

```text
운영 알림용: false positive를 줄이는 0.95 후보
탐지 분석용: recall/f1을 더 보는 0.8~0.9 후보
Agent 통합용: risk_probability 원점수와 risk_level을 함께 전달
```

## 21. Threshold 진단 해석

`risk_threshold_diagnostics.csv`는 같은 위험도 모델에서 threshold를 바꿨을 때 validation과 holdout 성능이 어떻게 변하는지 저장한다.

현재 선택된 `0.95`는 validation 기준으로 매우 보수적인 threshold다.

대표 후보는 다음처럼 해석할 수 있다.

```text
0.80 근처: recall과 f1을 더 살리는 후보
0.90 근처: precision과 f1 균형 후보
0.95: false positive 최소화 후보
```

이번 run의 validation 상위 후보를 보면 `0.85~0.95` 구간이 모두 좋은 후보로 들어왔다. 그중 `0.95`가 validation f1 0.6000과 false positive rate 0.0112를 동시에 만족해 선택되었다.

하지만 holdout에서는 threshold를 높일수록 false positive는 줄고 recall도 같이 줄어든다. 이 결과는 운영 목표에 따라 threshold를 다르게 정해야 함을 보여준다.

현재 프로젝트 목적이 “불필요한 현장 확인을 최소화하면서도 위험 신호를 놓치지 않는 것”이라면, 다음 실행에서는 `0.90`, `0.925`, `0.95`를 운영 후보로 비교하고, 각 후보의 holdout recall 손실을 함께 봐야 한다.

## 22. Group 진단 해석

`risk_group_diagnostics.csv` 기준으로 holdout false positive는 특정 그룹에 몰리는 경향이 있다.

눈에 띄는 지점은 다음과 같다.

```text
holdout manufacturer 2:
false_positive_rate 0.2069
true_positive 0

holdout configuration_type SH + DHW:
false_positive_rate 0.1629
true_positive 20

holdout season_bucket spring:
false_positive_rate 0.1429
true_positive 0

holdout split_regime_based train:
false_positive_rate 0.4737
true_positive 0
```

이 결과는 전체 holdout 성능 저하가 무작위로 발생했다기보다, 특정 manufacturer/configuration/season/regime 조합에서 정상 window를 위험으로 보는 문제가 남아 있음을 뜻한다.

특히 `manufacturer 2`, `spring`, `split_regime_based train` 그룹은 false positive가 높으면서 true positive가 거의 없거나 0이다. 이 그룹들은 위험 신호라기보다 데이터 분포 차이 또는 정상 운영 패턴 차이를 위험으로 오해했을 가능성이 있다.

다음 개선 후보는 다음과 같다.

```text
1. manufacturer/configuration별 threshold를 따로 검토한다.
2. season 또는 regime feature가 위험도 모델에서 과도하게 작동하는지 feature importance로 확인한다.
3. holdout에서 false positive가 집중되는 그룹을 07 explainability에서 우선 분석한다.
4. risk_probability를 그대로 Agent에 넘기고, Agent 단계에서 group별 보정 규칙을 둘지 검토한다.
```

## 23. 리드타임 결과

리드타임 모델 구조와 bucket은 이번 재설계에서 바꾸지 않았다.

따라서 리드타임 성능은 이전 run과 동일하다.

```text
validation accuracy: 0.4862
validation macro_f1: 0.3400
validation weighted_f1: 0.4576

holdout accuracy: 0.5785
holdout macro_f1: 0.3968
holdout weighted_f1: 0.5647
```

리드타임은 프로젝트 목적상 3중분류를 유지한다. 다만 `long_72h_plus` 구분이 약한 문제는 여전히 남아 있다.

## 24. 다음 진행 판단

이번 재설계로 위험도 모델의 알림 신뢰도는 좋아졌지만, 위험 탐지 민감도는 낮아졌다.

현재 선택지는 다음 두 가지다.

```text
1. 06을 한 번 더 조정한다.
   목적: threshold 0.90~0.95 사이에서 false positive와 recall 균형점을 찾는다.

2. 07로 넘어간다.
   목적: 현재 모델이 어떤 feature와 그룹에서 헛알림을 만드는지 근거 설명으로 확인한다.
```

현재는 07로 넘어가는 것이 더 유리하다. 이유는 threshold만 더 조정해도 성능 trade-off의 방향은 이미 확인되었기 때문이다. 이제는 왜 특정 그룹에서 false positive가 생기는지, 어떤 센서나 이벤트 feature가 위험도 판단을 끌어올리는지 확인해야 다음 06 개선 방향이 더 명확해진다.

따라서 추천 흐름은 다음과 같다.

```text
1. 현재 06 재설계 결과를 커밋한다.
2. 07 explainability에서 risk/leadtime feature importance와 그룹별 false positive 근거를 확인한다.
3. 07 결과를 보고 06의 feature set, group threshold, bucket 경계를 다시 조정한다.
```
