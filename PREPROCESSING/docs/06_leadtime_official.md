# 06 Leadtime Official

## 목적

현재 06 leadtime 계층에서 실제 기준으로 삼아야 하는 파일과 실행 진입점을 줄여서 고정한다.

## 현재 공식본

현재 leadtime 쪽은 promoted 3버킷 본을 기준으로 사용한다.

```text
data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv
data/processed/ml_leadtime/leadtime_bucket_metrics_promoted.csv
data/processed/ml_leadtime/leadtime_bucket_confusion_matrix_promoted.csv
```

holdout:

```text
accuracy   0.6512
macro_f1   0.4405
weighted   0.6432
top2_acc   0.9651
bucket_mae 0.3837
```

## canonical 실행 파일

```text
PREPROCESSING/osj/06_risk_leadtime_models.ipynb
```

지원 target:

```text
promoted_official -> pipeline_scripts/06_leadtime_model.py
```

공식 실행:

```text
PREPROCESSING/osj/06_risk_leadtime_models.ipynb
```

스크립트 직접 실행:

```bash
python PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
```

## 현재 판단

```text
leadtime는 promoted 3버킷 본을 유지한다.
현재는 추가 복잡도를 늘리는 것보다 이 출력을 Agent 입력으로 넘기는 것이 우선이다.
```

## legacy 참고자료

```text
PREPROCESSING/docs/06_test/06_leadtime_bucket_model.md
PREPROCESSING/osj/experiments/06_test/06_leadtime_bucket_model.ipynb
```

## 참고 문서

```text
PREPROCESSING/docs/06_leadtime_promotion_decision.md
```


