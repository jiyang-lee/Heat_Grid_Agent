# 2026-06-24 ML 07 작업 기록

이 문서는 06번 보강용 `split and normal audit` 작업 결과를 정리한다.

## 생성 파일

```text
PREPROCESSING/osj/06_risk_leadtime_audit.ipynb
PREPROCESSING/docs/06_risk_leadtime_audit.md
```

## 목적

06 audit은 모델 학습 단계가 아니다.
06번 LightGBM 위험도 모델 이후 holdout 붕괴 원인을 split, normal 기준, 제조사 분포, feature drift 관점에서 재현 가능하게 점검하는 audit 단계다.

## 입력

```text
data/processed/ml_risk/lgbm_risk_scores.csv
data/processed/ml_risk/models/risk_model_metadata.json
data/processed/ml_features/trainable_windows.csv
```

## 출력

```text
data/processed/ml_risk/holdout_split_label_diagnostics.csv
data/processed/ml_risk/holdout_error_diagnostics.csv
data/processed/ml_risk/holdout_feature_drift_diagnostics.csv
```

## 핵심 관찰

- holdout normal의 평균 risk가 holdout pre_fault보다 높다.
- manufacturer 2 normal의 risk가 특히 높다.
- false positive가 일부 substation에 몰린다.
- drift 상위 feature는 반환온도, 공급온도 변동성, network temperature gap 계열이다.

## 현재 결론

06 audit 결과는 holdout 붕괴가 단순 threshold 문제가 아니라 split/normal 기준 차이와 feature drift 문제에 가깝다는 점을 지지한다.

다음 단계는 순서상 07 explainability지만, 실제로는 06 기준 보강 또는 normal 기준 재정의를 먼저 검토하는 것이 더 타당하다.
