# 06 Risk Official

## 목적

현재 06 risk 계층에서 실제 기준으로 삼아야 하는 파일과 실행 진입점을 줄여서 고정한다.

이 문서만 보면 risk 쪽 06의 현재 운영 기준을 알 수 있어야 한다.

## 현재 공식본

현재 공식 risk 산출물은 calibrated 본이다.

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
data/processed/ml_risk/lgbm_risk_metrics_calibrated.csv
data/processed/ml_risk/lgbm_group_threshold_overrides.csv
```

holdout overall:

```text
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449
roc_auc   0.7628
ap        0.6197
```

## canonical 실행 파일

```text
PREPROCESSING/osj/06_risk_leadtime_models.ipynb
```

지원 target:

```text
calibrated_official  -> pipeline_scripts/06_risk_calibration.py
promoted_candidate   -> experiments/06_test/06_promoted_risk_model.py
```

공식 실행:

```text
PREPROCESSING/osj/06_risk_leadtime_models.ipynb
```

스크립트 직접 실행:

```bash
python PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
```

## 현재 판단

```text
official:
  calibrated 유지

candidate:
  promoted risk는 실험 결과로는 의미가 있었지만
  현재 공식 calibrated 본을 교체할 수준은 아니다.
```

## legacy 참고자료

기존 notebook 기반 설명 자료는 아래로 분리한다.

```text
PREPROCESSING/docs/06_test/06_risk_leadtime_model.md
PREPROCESSING/docs/06_test/06_risk_leadtime_audit.md
PREPROCESSING/osj/experiments/06_test/06_promoted_risk_model.py
PREPROCESSING/osj/experiments/06_test/06_risk_leadtime_model.ipynb
PREPROCESSING/osj/experiments/06_test/06_risk_leadtime_audit.ipynb
```

## 참고 문서

세부 근거는 아래 문서에 남아 있다.

```text
PREPROCESSING/docs/06_promotion_decision.md
PREPROCESSING/docs/06_next_improvement_plan.md
```



