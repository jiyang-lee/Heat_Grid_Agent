# 06 Test / Experiment Index

이 폴더는 공식 06/07 실행 흐름에 바로 포함되지 않는 실험, 감사, ablation, hyperparameter tuning 파일을 보관한다.

공식 실행은 아래 노트북과 스크립트를 기준으로 한다.

```text
PREPROCESSING/osj/06_risk_leadtime_models.ipynb
PREPROCESSING/osj/07_priority_engine.ipynb
PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py
```

## 승격된 실험

### Priority Engine threshold48

- 실험 파일: `07_priority_v2_threshold48.py`
- 공식 반영 위치: `PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py`
- 공식 엔진 버전: `priority_engine_v2_threshold48`
- 판단: threshold 48에서 holdout FPR `0.0000`을 유지하면서 recall/F1이 개선되어 공식 승격

## 보류된 실험

아래 실험은 기록과 비교용으로 유지하지만, 현재 공식 모델로 승격하지 않는다.

- `05_iforest_feature_hyperparam_experiment.py`
- `05_iforest_threshold_quantile_experiment.py`
- `06_anomaly_risk_integration_experiment.py`
- `06_combined_feature_experiment.py`
- `06_drift_feature_ablation.py`
- `06_event_context_reencoding_experiment.py`
- `06_event_context_state_experiment.py`
- `06_false_negative_audit.py`
- `06_false_negative_deep_audit.py`
- `06_feature_importance_audit.py`
- `06_hyperparameter_tuning_all.py`
- `06_hyperparameter_tuning_wide.py`
- `06_leadtime_improvement_experiments.py`
- `06_manufacturer2_sh_fp_audit.py`
- `06_risk_weighting_experiment.py`
- `06_state_thermal_combined_experiment.py`
- `06_thermal_anomaly_risk_blend_experiment.py`
- `06_thermal_feature_experiment.py`
- `07_priority_lgbm_regression_candidate.py`
- `07_priority_threshold_sweep_experiment.py`
- `07_priority_urgency_aux_experiment.py`

## 주요 보류 사유

- Isolation Forest threshold/hyperparameter 후보는 recall을 올릴 수 있으나 FPR 증가 가능성이 있어 공식 승격 전 추가 검증이 필요하다.
- Risk hyperparameter tuning은 validation에서는 개선처럼 보였지만 holdout에서 공식 모델보다 약했다.
- Leadtime tuning은 일부 지표가 소폭 개선됐지만 3-7d 버킷 안정성이 부족해 공식 승격하지 않았다.
- Priority LGBM regression 후보는 일부 성능이 좋아 보였으나 leadtime 출력 사용 방식에 leakage risk가 있어 공식 승격하지 않았다.

## 결과 위치

실험 결과 요약은 아래 폴더에 모은다.

```text
report/experiment_comparison
```

보고용 노트북은 아래 파일을 본다.

```text
report/anomaly_risk_leadtime_experiment_report.ipynb
report/hyperparameter_tuning_report.ipynb
```
