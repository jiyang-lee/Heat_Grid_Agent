# 05. baseline anomaly model 문서

이 문서는 `PREPROCESSING/osj/05_baseline_anomaly_model.ipynb`의 목적과 산출물 기준을 HeatGrid Agent 프로젝트 관점에서 정리한다.

05번 노트북은 04번에서 고정한 학습 입력 계약을 받아, 재현 가능한 이상탐지 baseline을 실제로 학습하고 점수와 임계값, 기본 평가 결과를 저장하는 단계다.

## 프로젝트 관점의 목적

HeatGrid Agent에서 ML은 최종 우선순위를 직접 계산하지 않는다.
대신 Agent가 해석 가능한 이상점수, 위험 신호, 근거 후보를 안정적으로 제공해야 한다.

이를 위해 05번에서는 다음을 수행한다.

- 정상 구간 중심 baseline 모델 학습
- 윈도우 단위 anomaly score 계산
- train 기준 threshold 계산
- time split과 substation split 기준 기본 성능 확인
- threshold 후보별 성능 비교
- 모델/스케일러 재사용 파일 저장
- 이후 06번 위험도/리드타임 단계에서 재사용할 score 저장

즉, 05번의 목적은 복잡한 최종 모델이 아니라, **정상 패턴 대비 얼마나 벗어났는지**를 재현 가능하게 계산하는 baseline을 만드는 것이다.

## 입력 데이터

05번은 04번 산출물을 사용한다.

기본 입력:

```text
data/processed/ml_features/trainable_windows.csv
data/processed/ml_features/feature_columns.csv
data/processed/ml_features/metadata_columns.csv
data/processed/ml_features/imputation_values.csv
```

기본 학습 입력 `trainable_windows.csv`는 strict 기준 + train 통계 기반 결측 대체가 이미 적용된 버전이다.

## baseline 구성

05번의 기준 모델은 `IsolationForest`다.
train split의 `normal` 행만 사용해 학습하고, 각 윈도우의 비정상 정도를 점수로 변환한다.

이 모델은 다음 목적에 적합하다.

- 정상 패턴 대비 이상징후 탐지
- 센서 조합이 평소와 다른 구간 탐지
- 기계실별 anomaly score 산출
- 06번 LightGBM 위험도 모델의 입력 feature 제공

05번 결과는 고장 확정 결과가 아니다.
`anomaly_score`는 “정상 패턴에서 얼마나 벗어났는가”를 나타내는 운영 이상도다.
이 점수는 legacy 06번 LightGBM 비교 실험에도 쓰이고, 새 canonical 후보인 paper-aligned Autoencoder 평가 체인과도 비교 기준을 공유한다.

## 학습 및 평가 기준

### 학습 데이터

모델 학습에는 다음 subset만 사용한다.

```text
split_time_based == train
label == normal
```

즉, anomaly baseline은 정상 패턴 기준 모델이다.

### 평가 데이터

기본 평가는 두 가지 split 기준으로 수행한다.

- `train`
- `validation`
- `holdout`

평가 split 컬럼:

- `split_time_based`
- `split_substation_based`

평가 타깃은 다음과 같이 이진화한다.

```text
normal -> 0
pre_fault -> 1
```

### threshold 기준

각 모델의 anomaly threshold는 train normal score 분포의 상위 quantile로 계산한다.

기본 기준:

```text
threshold = train_normal_score 99th percentile
```

기본 threshold는 99th percentile이다.
추가로 95th, 97.5th, 99th percentile threshold sweep 결과를 함께 저장한다.

## 저장 산출물

노트북은 아래 경로에 결과를 저장한다.

```text
data/processed/ml_baseline/
```

생성 파일:

- `anomaly_baseline_scores.csv`
  - 각 윈도우별 metadata + model score + threshold 기반 label

- `anomaly_baseline_metrics.csv`
  - split별 모델 성능 요약
  - 예: ROC-AUC, average precision, precision, recall, F1, false positive rate

- `anomaly_baseline_thresholds.csv`
  - 모델별 threshold 후보와 train normal score 요약

- `anomaly_baseline_threshold_sweep_metrics.csv`
  - threshold quantile별 split 성능 비교

- `models/standard_scaler.joblib`
  - 04번 feature 입력에 적용한 scaler

- `models/isolation_forest.joblib`
  - IsolationForest anomaly baseline 모델

- `models/baseline_model_metadata.json`
  - 모델 버전, feature 목록, 학습 필터, threshold 설정

## 다음 단계 연결

다음 단계는 두 갈래다.

1. 메인 IF + LightGBM 체인

- `06_risk_leadtime_model`
- `06_risk_leadtime_audit`
- `06_event_context_ablation`

2. 아카이브된 paper-aligned 체인

- `legacy/osj/06_paper_aligned_review`
- `legacy/osj/06_paper_aligned_data_selection`
- `legacy/osj/06_paper_aligned_autoencoder`
- `legacy/osj/06_paper_aligned_event_eval`
- `legacy/osj/06_paper_aligned_feature_attribution`
- `legacy/osj/06_paper_aligned_agent_contract`

legacy 06번에서는 05번 결과를 바탕으로 다음을 이어간다.

- faults.csv의 고장신고 시점 기준으로 고장신고 전 위험구간 라벨 생성
- sensor feature와 `anomaly_score`를 결합한 LightGBM 학습
- `disturbances.csv` 기반 최근 작업/정비 이력 feature 반영
- `risk_score` 또는 `risk_probability` 산출
- Agent와 Priority Engine 전달용 위험도 필드 설계

`PREPROCESSING/legacy` 아래 paper-aligned 06-P 계열에서는 다음을 이어간다.

- 정상 행동 구간 선정
- Autoencoder 기반 normal behaviour model 학습
- reconstruction error 기반 anomaly signal 계산
- criticality counter 및 event-wise detection 평가
- Agent / Priority Engine 계약 스키마 변환

05번의 핵심은 다음 한 문장으로 정리할 수 있다.

```text
Isolation Forest는 정상 패턴과 다른 이상징후를 찾는 baseline이며, 이 score는 legacy 비교와 paper-aligned 전환 판단의 공통 기준점이 된다.
```
