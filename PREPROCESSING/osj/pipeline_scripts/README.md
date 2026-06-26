# Pipeline Scripts

이 폴더는 공식 노트북에서 호출하는 Python 구현만 둔다.

직접 실행도 가능하지만, 기본 사용자는 `PREPROCESSING/osj` 루트의 노트북 순서를 따르는 것이 좋다.

## 공식 스크립트

- `06_risk_calibration.py`
  - 입력: `data/processed/ml_risk/lgbm_risk_scores.csv`
  - 출력: `data/processed/ml_risk/lgbm_risk_scores_calibrated.csv`
  - 역할: group threshold calibration 및 calibrated risk level 생성

- `06_leadtime_model.py`
  - 입력: `trainable_windows.csv`, risk scores, base leadtime metadata
  - 출력: promoted leadtime model/scores/metrics
  - 역할: 3-bucket promoted leadtime model 학습 및 산출물 생성

- `07_priority_engine.py`
  - 입력: calibrated risk scores, promoted leadtime scores
  - 출력: tuned priority engine scores/metadata
  - 역할: 설비실별 우선순위 점수 생성

## 실행 예

```powershell
python PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
python PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
python PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py
```
