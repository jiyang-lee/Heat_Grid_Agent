# HeatGrid ML Report Index

이 폴더는 프로젝트 보고용 노트북과 실험 비교 결과를 모은다.

## 보고용 노트북

### `heatgrid_ml_project_report.ipynb`

전체 ML 파이프라인 보고서다.
00~08 흐름, 데이터 구조, 모델 구조, 주요 산출물을 설명한다.

### `anomaly_risk_leadtime_experiment_report.ipynb`

anomaly, risk, leadtime 관련 성능 개선 실험을 비교한다.
공식 모델과 보류된 후보의 수치 차이를 확인하는 용도다.

### `hyperparameter_tuning_report.ipynb`

Isolation Forest, Risk LightGBM, Leadtime LightGBM의 hyperparameter tuning 결과를 정리한다.
튜닝 후보가 공식 모델보다 나은지 holdout 기준으로 비교한다.

## 실험 비교 폴더

```text
report/experiment_comparison
```

주요 파일:

- `05_iforest_threshold_quantile_summary.md`
- `06_experiment_comparison_summary.md`
- `06_hyperparameter_tuning_summary.md`
- `06_hyperparameter_tuning_wide_summary.md`
- `07_priority_threshold_sweep_summary.md`
- `07_priority_v2_threshold48_promotion.md`
- `07_priority_lgbm_regression_candidate_summary.md`
- `leadtime_bucket_confusion_official_vs_tuned.csv`

## 공식 판단 기준

보고서에 좋은 후보가 있어도 바로 공식 모델이 아니다.
공식 승격은 아래 위치에 반영된 경우에만 인정한다.

- `PREPROCESSING/osj/pipeline_scripts`
- `PREPROCESSING/osj` 루트 공식 노트북
- `PREPROCESSING/docs`
- `model_handoff`
