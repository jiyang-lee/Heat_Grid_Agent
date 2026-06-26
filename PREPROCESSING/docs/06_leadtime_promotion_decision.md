# 06 leadtime promotion decision

## 목적

leadtime 개선 실험에서 가장 현실적인 후보였던

```text
3버킷 유지
+ timeflow_lag_delta_roll3 추가
```

조합을 실제 승격 후보 산출물로 만들고, 기존 공식본과 비교한 기록이다.

## 실행 파일

```text
PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
```

## 출력 파일

```text
data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv
data/processed/ml_leadtime/leadtime_bucket_metrics_promoted.csv
data/processed/ml_leadtime/leadtime_bucket_confusion_matrix_promoted.csv
data/processed/ml_leadtime/models/lightgbm_leadtime_bucket_model_promoted.joblib
data/processed/ml_leadtime/models/leadtime_bucket_model_promoted_metadata.json
```

## 비교

### 기존 공식본 holdout

```text
accuracy   0.6512
macro_f1   0.4329
weighted   0.6385
top2_acc   0.9651
bucket_mae 0.3837
```

### promoted 후보 holdout

```text
accuracy   0.6512
macro_f1   0.4405
weighted   0.6432
top2_acc   0.9651
bucket_mae 0.3837
```

## 해석

- accuracy는 동일하다.
- macro F1은 소폭 개선된다.
- weighted F1도 소폭 개선된다.
- 거리 오차와 top-2 accuracy는 동일하다.

즉 큰 폭 개선은 아니지만, 적어도 현재 공식본보다 나빠지지는 않았고
분류 균형은 조금 좋아졌다.

## 결론

leadtime 쪽은 promoted 후보를 다음 공식 후보로 채택할 수 있다.

즉 현재 판단은 아래와 같다.

```text
risk:
  calibrated 공식본 유지

leadtime:
  promoted timeflow 후보를 차기 공식 후보로 채택 가능
```

## 운영 메모

아직 기존 파일을 덮어쓰지는 않았다.

따라서 구분은 아래처럼 본다.

```text
기존 공식본:
  leadtime_bucket_scores.csv
  leadtime_bucket_metrics.csv

차기 공식 후보:
  leadtime_bucket_scores_promoted.csv
  leadtime_bucket_metrics_promoted.csv
```

07/08 연결 전 마지막 선택만 남아 있는 상태다.

