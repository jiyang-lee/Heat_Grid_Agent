# HeatGrid Agent ML 인수 인덱스

이 문서는 HeatGrid Agent 프로젝트에서 ML 파트를 이어받을 때 먼저 읽는 인덱스다.

## 먼저 읽을 문서

- `PROJECT_ML_STATUS.md`
  - 현재 공식 모델 구조, 성능, 보류된 실험, 다음 개선 후보
- `agent_full_data_contract.md`
  - DB/Agent 전달용 raw, 전처리, feature, ML output, priority output 컬럼 계약
- `ML_OUTPUT_CONTRACT.md`
  - Agent가 받아야 하는 ML 출력 필드와 JSON/DataFrame 형태
- `ML_NOTEBOOK_PLAN.md`
  - 00~08 노트북 진행 계획
- `07_priority_engine.md`
  - Priority Engine 공식 점수 계산 방식

## 현재 공식 구조

```text
raw/context data
-> 03 preprocessing + windowing
-> 04 feature selection, 195 model input features
-> 05 Isolation Forest anomaly score
-> 06 LightGBM risk model
-> 06 LightGBM leadtime bucket model
-> 07 Priority Engine v2_threshold48
-> 08 Agent handoff package
```

## 모델 역할

- Isolation Forest: 정상 운전 패턴에서 벗어난 이상징후를 찾고 `anomaly_score`를 산출한다.
- LightGBM risk: 고장신고 전 위험구간과 유사한 패턴인지 판단해 `risk_score`와 `risk_probability`를 산출한다.
- LightGBM leadtime: 신고 기준 pseudo leadtime bucket을 추정한다.
- Priority Engine: anomaly/risk/leadtime을 조합해 오늘 또는 현재 먼저 볼 설비실 순위를 만든다.

ML은 고장을 확정하지 않는다.
ML은 Agent가 우선 점검 대상을 판단할 수 있도록 위험 신호와 근거를 제공한다.

## 현재 공식 성능 요약

### Risk

```text
holdout F1        0.5466
holdout recall    0.5116
holdout FPR       0.1449
holdout ROC-AUC   0.7628
```

### Leadtime

```text
holdout accuracy  0.6512
holdout macro F1  0.4405
holdout top2 acc  0.9651
```

`3-7d` 버킷은 샘플 수가 적어 신뢰도가 낮다.
Agent와 서비스에서는 leadtime을 확정 예측이 아니라 임박도 보조 신호로 써야 한다.

### Priority

```text
engine_version    priority_engine_v2_threshold48
holdout precision 1.0000
holdout recall    0.5116
holdout F1        0.6769
holdout FPR       0.0000
```

## 공식 실행 위치

노트북:

```text
PREPROCESSING/osj/00_load_dataset.ipynb
PREPROCESSING/osj/01_raw_inspection.ipynb
PREPROCESSING/osj/02_label_alignment.ipynb
PREPROCESSING/osj/03_preprocess_windows.ipynb
PREPROCESSING/osj/04_feature_selection.ipynb
PREPROCESSING/osj/05_baseline_anomaly_model.ipynb
PREPROCESSING/osj/06_risk_leadtime_models.ipynb
PREPROCESSING/osj/07_priority_engine.ipynb
PREPROCESSING/osj/08_model_handoff.ipynb
```

공식 Python 스크립트:

```text
PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py
```

## 실험과 공식의 경계

`PREPROCESSING/osj/experiments/06_test`는 실험 폴더다.
그 안의 파일은 공식 산출물 생성 대상이 아니다.

실험이 승격되면 반드시 아래 중 하나에 반영한다.

- `PREPROCESSING/osj/pipeline_scripts`
- `PREPROCESSING/osj` 루트 공식 노트북
- `PREPROCESSING/docs`
- `report/experiment_comparison`

현재 공식 승격된 실험은 Priority Engine `threshold48`이다.

## 보고서 위치

```text
report/heatgrid_ml_project_report.ipynb
report/anomaly_risk_leadtime_experiment_report.ipynb
report/hyperparameter_tuning_report.ipynb
report/experiment_comparison
```
