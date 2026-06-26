# 05. Isolation Forest 기반 이상탐지 모델

이 문서는 `PREPROCESSING/hsj/05_baseline_anomaly_model.ipynb`의 목적, 학습 전략, 성능 개선 기준, 산출물을 정리한다.

## 1. 목표

05 단계의 최우선 목표는 Isolation Forest 이상탐지 모델의 성능을 최대한 끌어올리는 것이다.

여기서 성능은 단순 정확도만 의미하지 않는다. 이상탐지는 라벨 불균형과 threshold 선택의 영향을 크게 받으므로 다음 지표를 함께 본다.

- `average_precision`: pre_fault 윈도우를 높은 anomaly score로 올리는 능력
- `roc_auc`: normal과 pre_fault score 분리 정도
- `precision`, `recall`, `f1`: threshold 적용 후 탐지 성능
- `false_positive_rate`: normal을 이상으로 잘못 잡는 비율

Isolation Forest는 비지도 모델이므로 학습에는 정상 데이터만 사용한다. 다만 모델 설정과 threshold 선택에는 validation split의 `normal`/`pre_fault` 라벨을 평가용으로 사용한다.

## 2. 입력

04 산출물을 입력으로 사용한다.

```text
data/processed/ml_features/trainable_windows.csv
data/processed/ml_features/feature_columns.csv
```

`feature_columns.csv`에서 `anomaly_feature == True`인 컬럼만 Isolation Forest 후보 feature로 사용한다.

현재 04 기준 anomaly feature는 다음과 같다.

```text
handoff Isolation Forest feature: 195개
현재 03 산출물에 존재하는 feature: 151개
누락 feature: 44개
```

05에서는 151개를 넘어서지 않는다. 추가 feature를 새로 만들지 않는다.

## 3. 학습 전략

### 3.1 학습 데이터

학습에는 다음 조건을 만족하는 row만 사용한다.

```text
label == normal
split == train
```

`use_for_supervised_training` 또는 `normal_reference_outlier` 컬럼이 있으면 다음 필터도 함께 적용한다.

```text
use_for_supervised_training == True
normal_reference_outlier != True
```

이렇게 하는 이유는 Isolation Forest가 정상 패턴을 학습하는 모델이기 때문이다. pre_fault 또는 품질이 의심되는 normal을 학습에 섞으면 정상 경계가 흐려져 anomaly score 분리력이 떨어질 수 있다.

### 3.2 평가 데이터

validation과 holdout에서는 다음 라벨만 평가에 사용한다.

```text
normal -> 0
pre_fault -> 1
```

`unlabeled`는 score 산출 대상에는 남길 수 있지만, 성능 지표 계산에서는 제외한다.

### 3.3 split 기준

05 노트북은 다음 split 컬럼을 후보로 평가한다.

```text
split_time_based
split_regime_based
```

기존 baseline handoff는 `split_time_based` 기준이지만, 현재 프로젝트의 성능 개선 목표를 고려해 `split_regime_based`도 함께 비교한다. validation 성능이 더 좋은 split 기준을 선택한다.

## 4. feature set 실험

Isolation Forest 후보 feature는 151개로 시작한다. 다만 결측률이 높은 feature는 이상탐지 모델의 거리/분리 구조를 흔들 수 있으므로 결측률 cutoff별 feature set을 비교한다.

비교 후보는 다음과 같다.

```text
missing_cutoff = 1.00  # 151개 전체 사용
missing_cutoff = 0.50
missing_cutoff = 0.40
missing_cutoff = 0.30
```

각 cutoff는 `feature_columns.csv`의 `missing_rate`를 기준으로 적용한다. 남는 feature가 너무 적으면 해당 실험은 건너뛴다.

## 5. 모델/threshold 실험

Isolation Forest는 다음 설정 조합을 비교한다.

```text
n_estimators: 300, 600
max_features: 0.8, 1.0
max_samples: auto
contamination: auto
random_state: 42
```

anomaly score는 다음처럼 정의한다.

```text
anomaly_score = -model.decision_function(X)
```

값이 클수록 정상 패턴에서 더 멀다고 해석한다.

threshold는 train normal score의 quantile로 정한다.

```text
0.80
0.85
0.90
0.925
0.95
0.975
0.99
```

초기 실행에서 `0.95` 이상 threshold가 너무 보수적으로 작동했기 때문에 낮은 quantile을 추가했다. validation에서 가장 좋은 설정을 선택한다. 현재 1차 선택 기준은 `f1`, 2차 기준은 `recall`, 3차 기준은 낮은 `false_positive_rate`, 4차 기준은 `average_precision`, 5차 기준은 `roc_auc`다.

## 6. 산출물

05는 다음 파일을 생성한다.

```text
data/processed/ml_baseline/anomaly_baseline_scores.csv
data/processed/ml_baseline/anomaly_model_metrics.csv
data/processed/ml_baseline/anomaly_experiment_results.csv
data/processed/ml_baseline/anomaly_selected_features.csv
data/processed/ml_baseline/models/isolation_forest_pipeline.joblib
data/processed/ml_baseline/models/isolation_forest.joblib
data/processed/ml_baseline/models/standard_scaler.joblib
data/processed/ml_baseline/models/median_imputer.joblib
data/processed/ml_baseline/models/baseline_model_metadata.json
```

`data/processed/`는 Git 추적 대상이 아니므로 산출물은 재생성 가능한 로컬 결과로 둔다.

대표 파일은 매 실행마다 덮어쓴다. 대신 마지막 셀에서 실행별 이력을 별도 폴더에 보관한다.

```text
data/processed/ml_baseline/runs/run_YYYYMMDD_HHMMSS/
data/processed/ml_baseline/anomaly_run_history.csv
data/processed/ml_baseline/anomaly_run_history_plot.png
```

`anomaly_run_history.csv`는 validation과 holdout의 주요 지표를 누적한다. `anomaly_run_history_plot.png`는 실행 순서별 `average_precision`, `roc_auc`, `f1`, `false_positive_rate` 추이를 보여준다.

또한 실행할 때마다 대표 CSV의 timestamp 버전을 추가로 저장한다.

```text
data/processed/ml_baseline/anomaly_model_metrics_run_YYYYMMDD_HHMMSS.csv
data/processed/ml_baseline/anomaly_experiment_results_run_YYYYMMDD_HHMMSS.csv
data/processed/ml_baseline/anomaly_baseline_scores_run_YYYYMMDD_HHMMSS.csv
data/processed/ml_baseline/anomaly_selected_features_run_YYYYMMDD_HHMMSS.csv
```

따라서 최신 결과는 고정 파일명으로 빠르게 확인하고, 과거 실행 결과는 run id가 붙은 파일이나 `runs/` 폴더에서 비교한다.

## 7. 후속 단계 연결

06 Risk LightGBM은 05의 `anomaly_baseline_scores.csv`에서 `anomaly_score`를 결합해 사용한다.

05의 최종 모델은 `baseline_model_metadata.json`에 다음 정보를 남긴다.

- 선택된 split 기준
- 선택된 missing cutoff
- 선택된 feature 목록
- 선택된 threshold quantile과 threshold 값
- validation/holdout 성능
- 모델 hyperparameter

## 8. 현재 단계의 판단

이번 05는 “무조건 많은 feature를 넣는 방식”보다 “기존 151개 anomaly feature 안에서 결측률 cutoff와 threshold를 비교해 validation 분리력을 높이는 방식”으로 진행한다.

이 판단의 이유는 다음과 같다.

- Isolation Forest는 feature scale과 결측 대체값에 민감하다.
- 결측률이 높은 feature는 특정 설비군을 비정상처럼 보이게 만들 수 있다.
- train normal 기준 threshold를 쓰면 운영 시 normal false alarm을 제어하기 쉽다.
- validation label을 threshold 선택에만 사용하면 비지도 학습의 성격을 유지하면서도 실제 탐지 성능을 개선할 수 있다.

## 9. 평가 지표 해석 방법

Isolation Forest 결과는 `anomaly_model_metrics.csv`와 `anomaly_experiment_results.csv`에서 확인한다.

각 지표는 다음처럼 해석한다.

- `average_precision`: pre_fault 윈도우가 anomaly score 상위권에 잘 올라오는지 본다. 라벨 불균형 상황에서는 단순 accuracy보다 이 지표가 더 유용하다. 다만 threshold 적용 후 실제 탐지 성능을 직접 보여주지는 않는다.
- `roc_auc`: normal과 pre_fault score 분포가 전반적으로 얼마나 잘 분리되는지 본다. 0.5면 무작위에 가깝고, 0.7 이상이면 분리 신호가 있다고 볼 수 있다.
- `precision`: 이상으로 잡은 것 중 실제 pre_fault 비율이다. 낮으면 false alarm이 많다는 뜻이다.
- `recall`: 전체 pre_fault 중 이상으로 잡은 비율이다. 낮으면 위험 구간을 놓치고 있다는 뜻이다.
- `f1`: precision과 recall의 균형 지표다. threshold 적용 후 실제 탐지 성능을 볼 때 사용한다.
- `false_positive_rate`: normal을 이상으로 잘못 잡은 비율이다. 운영 알림 피로도와 직접 연결된다.

이상탐지에서는 accuracy를 핵심 지표로 보지 않는다. normal이 많은 데이터에서는 모두 normal로 예측해도 accuracy가 높게 나올 수 있기 때문이다.

## 10. 현재 결과 해석

현재 1차 실행 결과 기준 최종 선택 모델은 다음 설정이다.

```text
split_column: split_time_based
missing_cutoff: 0.3
feature_count: 112
n_estimators: 300
max_features: 0.8
threshold_quantile: 0.95
```

현재 validation 결과는 다음과 같다.

```text
average_precision: 0.5735
roc_auc: 0.7211
precision: 0.0
recall: 0.0
f1: 0.0
false_positive_rate: 0.0
```

holdout 결과는 다음과 같다.

```text
average_precision: 0.5225
roc_auc: 0.6074
precision: 1.0
recall: 0.0071
f1: 0.0142
false_positive_rate: 0.0
```

이 결과는 두 가지로 나누어 해석해야 한다.

첫째, score ranking 관점에서는 완전히 나쁜 결과는 아니다. validation `average_precision 0.5735`, `roc_auc 0.7211`은 anomaly score가 pre_fault를 어느 정도 상위권으로 올리고 있다는 뜻이다.

둘째, 현재 threshold 기준 탐지 성능은 아직 부족하다. validation에서 precision, recall, f1이 모두 0이라는 것은 선택된 threshold를 적용했을 때 validation pre_fault가 하나도 탐지되지 않았다는 뜻이다. holdout에서도 recall이 0.0071로 매우 낮다. 즉 모델의 score 자체에는 신호가 있지만, 운영 threshold가 너무 보수적이거나 score 분포가 split마다 달라진 상태로 볼 수 있다.

따라서 현재 모델은 “score ranking baseline은 의미가 있으나, 알림/탐지 threshold는 개선 필요” 단계로 판단한다.

## 11. 다음 성능 개선 방향

성능 개선은 다음 순서로 진행하는 것이 좋다.

1. threshold 후보를 더 낮은 quantile까지 넓힌다.

현재 후보는 `0.80`, `0.85`, `0.90`, `0.925`, `0.95`, `0.975`, `0.99`다. 낮은 threshold는 recall을 높일 수 있지만 false positive도 함께 증가할 수 있다. 따라서 f1과 false positive rate를 같이 본다.

2. 모델 선택 기준에 threshold 기반 f1 또는 recall을 더 강하게 반영한다.

초기 실험에서는 `average_precision`을 1차 기준으로 선택했다. score ranking은 좋지만 threshold 탐지가 약한 모델이 선택될 수 있다는 문제가 확인되어, 현재 노트북은 `f1 -> recall -> 낮은 false_positive_rate -> average_precision -> roc_auc` 순서로 최종 후보를 선택한다.

3. split별 threshold를 따로 비교한다.

현재는 train normal score quantile로 threshold를 잡는다. validation/holdout score 분포가 다르면 threshold가 너무 보수적으로 작동할 수 있다. split별 score 분포를 시각화해 threshold 위치가 pre_fault 분포와 겹치는지 확인한다.

4. 결측률 cutoff 후보를 더 세분화한다.

현재 선택은 `missing_cutoff 0.3`, 112개 feature다. 다음에는 `0.2`, `0.25`, `0.35`를 추가해 결측률이 낮은 feature 중심 모델이 더 안정적인지 확인한다.

5. feature family 단위 ablation을 진행한다.

`시간/주기`, `센서 통계`, `이벤트 이력`을 각각 제거하거나 조합해 어떤 family가 anomaly ranking을 개선하는지 본다. 특히 이벤트 이력 feature는 risk 모델에는 유용하지만 순수 이상탐지에서는 label proxy처럼 작동할 가능성이 있으므로 별도 비교가 필요하다.

6. manufacturer/configuration별 score 분포를 확인한다.

특정 제조사나 설비 구성에서 false positive가 집중되면 전역 threshold 하나로는 부족할 수 있다. 이 경우 group별 threshold 또는 group별 normal reference 모델을 검토한다.

7. `contamination`을 고정값으로 비교한다.

현재는 `contamination="auto"`다. 다음 실험에서는 `0.03`, `0.05`, `0.08`, `0.10`을 비교해 score 분포와 threshold 탐지 성능이 좋아지는지 확인한다.

8. threshold 선택 기준을 운영 목적별로 나눈다.

초기에는 validation `average_precision`을 가장 먼저 봤다. score ranking을 개선하는 데는 좋지만, 실제 알림 성능은 f1 또는 recall이 더 중요하므로 현재는 탐지 균형 우선 기준을 기본값으로 둔다. 이후 필요하면 다음 선택 기준을 비교한다.

```text
ranking 우선: average_precision -> f1 -> recall
탐지 균형 우선: f1 -> recall -> false_positive_rate -> average_precision
조기 경보 우선: recall -> false_positive_rate -> average_precision
```

9. calibration용 validation threshold를 별도로 둔다.

train normal quantile threshold는 운영 안정성이 좋지만, split 변화가 크면 너무 보수적일 수 있다. validation에서 precision-recall curve를 보고 목표 recall 또는 목표 false positive rate에 맞는 threshold를 별도로 고르는 방식을 비교한다.

10. 정상 학습 데이터 품질을 더 엄격하게 만든다.

normal 중에서도 결측률이 높거나 `normal_reference_outlier == True`인 row는 정상 경계를 흐릴 수 있다. 이미 outlier 필터를 적용하지만, 다음 실험에서는 `missing_rate`, `timestamp_gap_count`, `sensor_error_candidate_count` 기준으로 train normal을 더 좁혀볼 수 있다.

11. feature family별 모델을 비교한다.

현재는 선택된 anomaly feature를 함께 사용한다. 다음 실험에서는 다음 조합을 비교한다.

```text
센서 통계만
센서 통계 + 시간/주기
센서 통계 + 이벤트 이력
센서 통계 + 시간/주기 + 이벤트 이력
```

이 비교를 통해 이벤트 이력이 anomaly score를 실제 이상 신호로 개선하는지, 아니면 label에 가까운 proxy처럼 작동하는지 확인한다.

## 13. 성능 개선 기록 방식

threshold를 낮춰 재실행하면 다음 파일들이 자동으로 쌓인다.

```text
anomaly_run_history.csv
anomaly_run_history_plot.png
anomaly_model_metrics_run_YYYYMMDD_HHMMSS.csv
anomaly_experiment_results_run_YYYYMMDD_HHMMSS.csv
```

`anomaly_run_history.csv`에는 이전 최고 성능 대비 변화량도 함께 기록한다.

```text
delta_vs_previous_best_average_precision
delta_vs_previous_best_roc_auc
delta_vs_previous_best_f1
delta_vs_previous_best_recall
delta_vs_previous_best_false_positive_rate
```

`average_precision`, `roc_auc`, `f1`, `recall`은 값이 커질수록 개선이다. `false_positive_rate`는 값이 낮아질수록 개선이다.

성능이 조금이라도 좋아졌는지는 다음 순서로 판단한다.

1. validation `f1` 또는 `recall`이 0에서 벗어났는지 본다.
2. false positive rate가 과도하게 증가하지 않았는지 본다.
3. average precision과 roc auc가 크게 무너지지 않았는지 본다.
4. holdout에서도 같은 방향의 개선이 반복되는지 본다.

현재 문제는 score ranking보다 threshold 적용 후 recall이 낮은 점이다. 따라서 다음 실행에서 가장 먼저 볼 변화는 validation `recall`과 `f1`이다.

## 14. 2026-06-26 f1 우선 기준 실행 결과

`average_precision` 우선 기준에서 `f1 -> recall -> 낮은 false_positive_rate -> average_precision -> roc_auc` 기준으로 바꾼 뒤 다시 실행했다.

선택된 모델 설정은 다음과 같다.

```text
run_id: run_20260626_144708
model_key: split_time_based|0.4|300|1.0|0.8
split_column: split_time_based
missing_cutoff: 0.4
feature_count: 130
n_estimators: 300
max_features: 1.0
threshold_quantile: 0.8
threshold: -0.043719924842822194
```

이전 `threshold 0.8 + average_precision 우선` 실행과 비교하면 다음과 같다.

```text
validation f1: 0.2162 -> 0.3980
validation recall: 0.1280 -> 0.3120
validation precision: 0.6957 -> 0.5493
validation false_positive_rate: 0.0258 -> 0.1181
validation average_precision: 0.5735 -> 0.4789
validation roc_auc: 0.7211 -> 0.6334
```

```text
holdout f1: 0.3923 -> 0.4681
holdout recall: 0.2929 -> 0.3929
holdout precision: 0.5942 -> 0.5789
holdout false_positive_rate: 0.1049 -> 0.1498
holdout average_precision: 0.5225 -> 0.6028
holdout roc_auc: 0.6074 -> 0.7077
```

이번 결과는 탐지 성능 관점에서는 개선이다. validation과 holdout 모두 `f1`과 `recall`이 올라갔다. 특히 holdout에서는 `average_precision`과 `roc_auc`도 함께 좋아졌기 때문에, 완전히 과적합된 선택으로 보기는 어렵다.

다만 운영 관점에서는 주의가 필요하다. false positive rate가 validation 약 11.8%, holdout 약 15.0%까지 올라갔다. 이는 정상 구간 중 일부가 이상으로 잡혀 현장 확인 부담을 늘릴 수 있다는 뜻이다.

현재 판단은 다음과 같다.

```text
탐지력 개선: 성공
알림 신뢰도: 추가 개선 필요
다음 목표: f1/recall을 유지하면서 false_positive_rate 낮추기
```

다음 실험은 threshold를 더 낮추기보다, 같은 `0.8` 근처에서 false positive를 줄이는 방향이 우선이다.

추천 실험 순서는 다음과 같다.

1. 선택 기준을 `f1 -> 낮은 false_positive_rate -> precision -> recall -> average_precision`으로 바꿔본다.
2. threshold 후보에 `0.825`, `0.85`, `0.875`를 추가해 `0.8`보다 조금 보수적인 지점에서 f1과 false positive 균형을 찾는다.
3. `missing_cutoff 0.35`, `0.45`를 추가해 112개와 130개 사이 feature 수를 비교한다.
4. manufacturer/configuration별 false positive 분포를 확인한다.
5. false positive가 특정 group에 몰리면 group별 threshold를 검토한다.

## 12. 다음 노트북 개선 후보

05 노트북에 추가하면 좋은 시각화는 다음과 같다.

- normal/pre_fault anomaly score 분포 히스토그램
- threshold line이 포함된 validation score 분포
- precision-recall curve
- ROC curve
- manufacturer/configuration별 score boxplot
- run history 기반 지표 추이 그래프

이 중 가장 먼저 추가할 것은 validation score 분포와 precision-recall curve다. 현재 문제는 ranking보다 threshold 탐지 성능에 있으므로, threshold가 실제 pre_fault score 분포의 어느 위치에 놓이는지를 확인하는 것이 우선이다.
