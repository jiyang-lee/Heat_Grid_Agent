# 06-P2. paper-aligned autoencoder 문서

이 문서는 `PREPROCESSING/legacy/osj/06_paper_aligned_autoencoder.ipynb`의 목적과 산출물 기준을 정리한다.

## 목적

- 정상 행동 구간만으로 Autoencoder baseline 학습
- reconstruction error 계산
- anomaly score 정규화 규칙 고정

## 핵심 원칙

- 모델은 고장을 분류하지 않는다.
- 출력은 정상 행동에서 얼마나 벗어났는지 나타내는 이상징후 신호다.
- 학습과 스코어링 경로는 재현 가능하게 저장한다.
- 현재 프로젝트 환경 제약상 baseline은 `sklearn MLPRegressor 재구성형 autoencoder`로 구현한다.

## 입력

```text
data/processed/paper_aligned/normal_behaviour_training_windows.csv
data/processed/paper_aligned/event_evaluation_windows.csv
data/processed/ml_windows/ml_window_dataset.csv
data/processed/ml_features/feature_columns.csv
data/processed/ml_features/imputation_values.csv
```

## 모델 고정값

```text
model_version: paper_aligned_autoencoder_v1
model_type: sklearn_mlp_autoencoder_regressor
hidden_layer_sizes: (64, 32, 64)
random_state: 42
feature_count: 136
```

anomaly score 정의:

```text
reconstruction_rmse = window 단위 재구성 오차
anomaly_score = reconstruction_rmse / train_rmse_p099
```

즉 `anomaly_score >= 1.0`은 train normal 99% 분위수를 넘는 point anomaly 기준선이다.

## 출력

```text
data/processed/paper_aligned/autoencoder_reconstruction_scores.csv
data/processed/paper_aligned/autoencoder_thresholds.csv
data/processed/paper_aligned/models/paper_aligned_autoencoder_model.joblib
data/processed/paper_aligned/models/paper_aligned_autoencoder_scaler.joblib
data/processed/paper_aligned/models/autoencoder_metadata.json
```

현재 생성 결과:

```text
model_version: paper_aligned_autoencoder_v1
feature_count: 136
hidden_layer_sizes: (64, 32, 64)
train_rows: 1216
validation_rows: 269
n_iter: 19

train_rmse_mean: 0.6308
validation_rmse_mean: 0.6459

train_rmse_p095: 1.1178
train_rmse_p0975: 1.2720
train_rmse_p099: 1.4867
```

event evaluation subset 요약:

```text
validation normal:
  rows 280
  anomaly_mean 0.4303
  above_p099 3

validation fault:
  rows 166
  anomaly_mean 1.4096
  above_p099 30

holdout normal:
  rows 304
  anomaly_mean 0.4311
  above_p099 8

holdout fault:
  rows 104
  anomaly_mean 0.6735
  above_p099 11
```

주의:

- 이 단계의 `above_p099`는 point anomaly 개수일 뿐이다.
- 최종 detection은 06-P3에서 criticality counter를 적용한 뒤 event-wise로 평가한다.

`autoencoder_reconstruction_scores.csv` 핵심 컬럼:

```text
manufacturer
substation_id
window_start
window_end
event_type
event_id
event_split
selected_for_autoencoder_train
selected_for_autoencoder_validation
selected_for_event_eval
selected_for_event_tuning
selected_for_event_holdout
reconstruction_mse
reconstruction_rmse
anomaly_score
is_above_train_p095
is_above_train_p0975
is_above_train_p099
```

## 다음 단계 연결

이 단계 결과는 `06_paper_aligned_event_eval.ipynb`에서 criticality counter와 event-wise detection 평가의 입력으로 사용한다.
