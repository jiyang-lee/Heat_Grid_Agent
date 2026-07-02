# PREPROCESSING/osj Flow

이 폴더는 HeatGrid Agent ML 파이프라인의 공식 실행 흐름을 담는다.

루트에는 사람이 순서대로 실행할 노트북만 둔다.
세부 Python 구현은 `pipeline_scripts/`, 실험/감사 코드는 `experiments/`, 공식 흐름에서 제외된 구버전 진입점은 `archive/`에 둔다.

## 공식 실행 순서

```text
00_load_dataset.ipynb
01_raw_inspection.ipynb
02_label_alignment.ipynb
03_preprocess_windows.ipynb
04_feature_selection.ipynb
05_baseline_anomaly_model.ipynb
06_risk_leadtime_models.ipynb
07_priority_engine.ipynb
08_model_handoff.ipynb
```

## 단계별 역할

- `00_load_dataset.ipynb`: PreDist 데이터 로드/배치 확인
- `01_raw_inspection.ipynb`: raw operational/context 데이터 구조 확인
- `02_label_alignment.ipynb`: fault, disturbance, normal event 정렬
- `03_preprocess_windows.ipynb`: 전처리, windowing, feature engineering 기반 생성
- `04_feature_selection.ipynb`: 모델 입력 feature 195개 계약 고정
- `05_baseline_anomaly_model.ipynb`: Isolation Forest anomaly score 생성
- `06_risk_leadtime_models.ipynb`: LightGBM risk calibration 및 3-bucket leadtime 모델 생성
- `07_priority_engine.ipynb`: anomaly/risk/leadtime 기반 설비실 점검 우선순위 생성
- `08_model_handoff.ipynb`: Agent/서비스 전달용 모델 패키지 검증

## 현재 공식 모델 기준

- 이상탐지: `Isolation Forest`
- 위험도: `LightGBM risk model + calibrated threshold`
- 리드타임: `LightGBM 3-bucket leadtime model`
- 우선순위: `priority_engine_v2_threshold48`

ML 결과는 고장 확정이 아니다.
Agent와 Priority Engine이 사용할 이상점수, 위험도, 리드타임, 우선순위 근거를 제공하는 보조 신호다.

## 공식 Python 스크립트

공식 노트북에서 호출하는 Python 구현은 아래 세 개다.

```text
pipeline_scripts/06_risk_calibration.py
pipeline_scripts/06_leadtime_model.py
pipeline_scripts/07_priority_engine.py
```

직접 실행할 때는 아래 순서를 따른다.

```powershell
python PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
python PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
python PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py
```

## 실험 폴더 기준

`experiments/06_test` 아래 파일은 성능 개선, 감사, ablation, hyperparameter tuning 실험용이다.
공식 산출물을 만드는 필수 실행 대상이 아니다.

실험 결과가 공식 흐름으로 승격된 경우에만 `pipeline_scripts/` 또는 루트 노트북에 반영한다.
현재 승격된 실험 기준은 Priority Engine의 `threshold48` 조정이다.

## 문서와 보고서

핵심 인계 문서는 아래를 먼저 본다.

```text
PREPROCESSING/docs/ML_HANDOFF.md
PREPROCESSING/docs/PROJECT_ML_STATUS.md
PREPROCESSING/docs/agent_full_data_contract.md
```

보고용 노트북과 실험 비교표는 루트의 `report/` 폴더에 있다.

## 산출물 기준

최종 전달 모델 패키지는 아래 폴더에서 관리한다.

```text
model_handoff/heatgrid_ml_models_2026-06-25
```

이 패키지는 `08_model_handoff.ipynb`에서 검증한다.
