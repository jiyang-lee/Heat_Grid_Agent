# HeatGrid Prediction + Priority Model Handoff

이 패키지는 기존 예측 모델 handoff(IF + LGBM risk + LGBM leadtime)에 proto 완성본 우선순위 LGBM 회귀모델을 추가한 통합 전달 ZIP이다.

## 구조

```text
heatgrid_prediction_priority_models_2026-06-26/
├─ anomaly/
│  ├─ standard_scaler.joblib
│  ├─ isolation_forest.joblib
│  └─ baseline_model_metadata.json
├─ risk/
│  ├─ lightgbm_risk_model.joblib
│  ├─ risk_model_group_calibration.json
│  └─ risk_model_metadata.json
├─ leadtime/
│  ├─ lightgbm_leadtime_bucket_model_promoted.joblib
│  └─ leadtime_bucket_model_promoted_metadata.json
├─ priority/
│  ├─ priority_engine_tuned_metadata.json
│  ├─ lightgbm_priority_model.joblib
│  └─ priority_model_metadata.json
├─ docs/
├─ MANIFEST.json
└─ README.md
```

## 추론 흐름

```text
raw/preprocessed window
-> feature adapter
-> Isolation Forest anomaly
-> LGBM risk
-> LGBM leadtime
-> LGBM priority regression
-> priority_score / priority_level
```

## Priority 회귀모델

`priority/lightgbm_priority_model.joblib`은 `model_chain_output.csv`의 7개 feature를 입력으로 받는다. feature 순서와 학습/평가 metadata는 `priority/priority_model_metadata.json`을 기준으로 한다.

기존 `priority/priority_engine_tuned_metadata.json`는 예전 rule engine metadata로 보존했다. proto 완성본의 기본 priority 산출은 LGBM 회귀모델 기준이다.
