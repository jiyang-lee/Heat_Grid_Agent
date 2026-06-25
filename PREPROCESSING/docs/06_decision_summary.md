# 06 Decision Summary

## 목적

06 관련 파일이 많기 때문에, 실제로 지금 무엇을 기준으로 써야 하는지 한 장에 고정한다.

이 문서가 06의 현재 canonical index다.

## 사용 원칙

```text
1. 지금 실제 실행은 official / experiments / audit entrypoint만 본다.
2. notebook 기반 legacy 참고자료는 06_test 폴더로 분리한다.
3. 새 작업을 재개할 때는 이 문서부터 읽는다.
```

## 지금 써야 하는 출력

### risk 공식본

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
data/processed/ml_risk/lgbm_risk_metrics_calibrated.csv
```

### leadtime 공식본

```text
data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv
data/processed/ml_leadtime/leadtime_bucket_metrics_promoted.csv
```

## 지금 봐야 하는 실행 파일

```text
official:
  PREPROCESSING/osj/06_risk_official.py
  PREPROCESSING/osj/06_leadtime_official.py

experiments:
  PREPROCESSING/osj/06_risk_experiments.py
  PREPROCESSING/osj/06_leadtime_experiments.py

audit:
  PREPROCESSING/osj/06_risk_audit.py
```

## 지금 봐야 하는 문서

```text
PREPROCESSING/docs/06_risk_official.md
PREPROCESSING/docs/06_leadtime_official.md
PREPROCESSING/docs/06_experiment_log.md
PREPROCESSING/docs/06_audit_summary.md
PREPROCESSING/docs/06_decision_summary.md
```

## 해석

```text
1. 공식 산출물은 risk / leadtime 각각 하나씩만 본다.
2. 나머지 06 세부 문서는 reference다.
3. 새로 이어서 작업할 때는 이 문서와 위 4개 문서부터 읽으면 된다.
```

## legacy 참고자료 위치

```text
PREPROCESSING/docs/06_test/
PREPROCESSING/osj/06_test/
```
