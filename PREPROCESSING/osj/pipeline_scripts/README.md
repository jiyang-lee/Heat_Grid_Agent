# Pipeline Scripts

이 폴더는 공식 노트북에서 호출하는 Python 구현만 둔다.

기본 사용자는 `PREPROCESSING/osj` 루트의 노트북 순서를 따른다.
자동 실행이나 재현 검증이 필요할 때만 아래 스크립트를 직접 실행한다.

## 공식 스크립트

### `06_risk_calibration.py`

- 입력: `data/processed/ml_risk/lgbm_risk_scores.csv`
- 출력: `data/processed/ml_risk/lgbm_risk_scores_calibrated.csv`
- 역할: LightGBM risk score에 group calibration과 calibrated risk level을 적용한다.
- 현재 공식 holdout 기준: F1 `0.5466`, recall `0.5116`, FPR `0.1449`

### `06_leadtime_model.py`

- 입력: `trainable_windows.csv`, risk scores, base leadtime metadata
- 출력: `data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv`
- 역할: 3-bucket leadtime 모델을 학습하고 리드타임 확률/버킷을 산출한다.
- 현재 공식 holdout 기준: accuracy `0.6512`, macro F1 `0.4405`, top2 accuracy `0.9651`
- 주의: `3-7d` 버킷은 샘플 수가 적어 신뢰도가 낮다.

### `07_priority_engine.py`

- 입력: calibrated risk scores, promoted leadtime scores
- 출력: `data/processed/ml_priority/priority_engine_scores_tuned.csv`
- 역할: 설비실별 점검 우선순위 점수와 level을 생성한다.
- 현재 공식 엔진 버전: `priority_engine_v2_threshold48`
- 현재 공식 holdout 기준: precision `1.0000`, recall `0.5116`, F1 `0.6769`, FPR `0.0000`

## 실행 예

```powershell
python PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
python PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
python PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py
```

## 관리 원칙

- 실험용 코드는 이 폴더에 두지 않는다.
- 공식 산출물 생성에 필요한 코드만 유지한다.
- 실험이 승격되면 이 폴더의 공식 스크립트에 반영하고, 실험 기록은 `experiments/06_test`와 `report/experiment_comparison`에 남긴다.
