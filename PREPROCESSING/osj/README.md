# PREPROCESSING/osj Flow

이 폴더는 HeatGrid Copilot ML 파이프라인의 공식 실행 흐름을 담는다.

루트에는 사람이 순서대로 실행할 노트북만 둔다.
세부 Python 구현은 `pipeline_scripts/`, 실험/감사 코드는 `experiments/`, 더 이상 공식이 아닌 구버전 진입점은 `archive/`에 둔다.

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
- `03_preprocess_windows.ipynb`: windowing 및 feature engineering 기반 생성
- `04_feature_selection.ipynb`: 모델 입력 feature 195개 계약 고정
- `05_baseline_anomaly_model.ipynb`: Isolation Forest anomaly score 생성
- `06_risk_leadtime_models.ipynb`: risk calibration 및 promoted leadtime 모델 생성
- `07_priority_engine.ipynb`: anomaly/risk/leadtime 기반 priority score 생성
- `08_model_handoff.ipynb`: Agent/서비스 전달용 모델 패키지 검증

## 하위 폴더

- `pipeline_scripts/`: 공식 노트북에서 호출하는 Python 구현
- `experiments/`: 실험, audit, ablation, false negative 분석
- `archive/`: 구버전 wrapper 또는 공식 흐름에서 제외된 파일

## 06 기준

06은 예전처럼 여러 파일을 직접 고르는 방식이 아니라 아래 노트북 하나를 기준으로 실행한다.

```text
06_risk_leadtime_models.ipynb
```

내부적으로 호출하는 공식 스크립트는 다음이다.

```text
pipeline_scripts/06_risk_calibration.py
pipeline_scripts/06_leadtime_model.py
```

`experiments/06_test` 아래 파일은 공식 산출물 생성을 위한 필수 실행 대상이 아니다.

## 07 기준

공식 Priority Engine은 tuned 버전을 기준으로 한다.

```text
pipeline_scripts/07_priority_engine.py
```

구버전 basic priority script는 `archive/07_priority_engine_basic.py`로 이동했다.

## 산출물 기준

최종 전달 모델 패키지는 아래 폴더에서 관리한다.

```text
model_handoff/heatgrid_ml_models_2026-06-25
```

이 패키지는 `08_model_handoff.ipynb`에서 검증한다.
