# 06-C. pseudo lead time bucket 문서

## 현재 canonical index

```text
PREPROCESSING/docs/06_decision_summary.md
PREPROCESSING/docs/06_leadtime_official.md
```

## 목적

이 문서는 `PREPROCESSING/osj/experiments/06_test/06_leadtime_bucket_model.ipynb`에서 구현한
legacy pseudo leadtime bucket 모델을 정리한다.

현재 이 문서는 메인 `Isolation Forest + LightGBM` 06 체인 내부에서
leadtime 분류 기준과 역할을 설명하는 참고 문서다.

## target bucket

```text
0-24h
1-3d
3-7d
```

즉 normal 행은 이 모델의 직접 학습 대상이 아니다.

## 모델 구조

기본 모델:

```text
LightGBM multiclass classifier
```

설명:

- risk model은 `normal vs pre_fault`를 구분한다.
- leadtime model은 `pre_fault 내부에서 시간 bucket`을 구분한다.
- 두 모델은 역할이 다르므로 분리한다.

## split / 평가

split 기준:

```text
split_event_based
```

평가 지표:

- accuracy
- macro F1
- weighted F1
- top-2 accuracy
- bucket distance MAE

## 출력

```text
data/processed/ml_leadtime/leadtime_bucket_scores.csv
data/processed/ml_leadtime/leadtime_bucket_metrics.csv
data/processed/ml_leadtime/leadtime_bucket_confusion_matrix.csv
data/processed/ml_leadtime/models/lightgbm_leadtime_bucket_model.joblib
data/processed/ml_leadtime/models/leadtime_bucket_model_metadata.json
```

## 현재 위치

현재 운영 기준은 legacy 기본본이 아니라 promoted 3버킷 본이다.

```text
data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv
data/processed/ml_leadtime/leadtime_bucket_metrics_promoted.csv
```

따라서 이 문서는 구조 설명용 참고 자료로 읽으면 된다.

