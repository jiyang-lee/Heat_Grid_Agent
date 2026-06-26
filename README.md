# HeatGrid Agent

HeatGrid Agent는 지역난방 서브스테이션 운영 데이터를 입력으로 받아 이상 탐지, 위험도, 리드타임, 작업 우선순위 신호를 생성하는 ML 프로젝트입니다.

이 저장소에는 데이터 전처리와 실험 과정, 학습된 모델 산출물, 전달용 모델 패키지, 실제 운영 프로젝트에 붙일 수 있는 추론 패키지가 함께 들어 있습니다.

## 현재 결론

외부 프로젝트에 단순히 모델 파일만 넘기면 충분하지 않습니다.

운영 데이터가 실시간 또는 배치로 들어왔을 때는 학습 때와 동일한 전처리, 6시간 윈도우 생성, 피처 엔지니어링, 결측치 보정, 카테고리 매핑, 모델 추론 절차가 필요합니다.

따라서 전달 목적에 따라 아래처럼 구분합니다.

```text
model_handoff/heatgrid_ml_models_2026-06-25/
```

위 폴더는 모델 중심 전달용입니다. 대상 프로젝트가 이미 동일한 전처리와 피처 생성 로직을 가지고 있을 때만 사용합니다.

```text
inference_handoff/heatgrid_inference_package_2026-06-26/
```

위 폴더는 실제 운영 프로젝트 연동용입니다. 모델뿐 아니라 원천 운영 데이터에서 추론 결과를 만들기 위한 전처리, 피처 엔지니어링, 스코어링 코드와 계약 파일을 포함합니다.

## 전체 처리 흐름

```text
원천 운영 데이터
  -> 라벨/설비 메타데이터 정렬
  -> 6시간 윈도우 전처리
  -> 피처 생성 및 결측치 보정
  -> 이상 탐지 모델
  -> 위험도 모델 및 그룹별 보정
  -> 리드타임 모델
  -> 우선순위 산정 엔진
```

## 저장소 구조

```text
data/
  raw_data/                  Predist, XAI4Heat 원천 데이터
  processed/                 전처리 및 모델 학습 과정에서 생성된 산출물

PREPROCESSING/
  osj/                       주요 노트북, 파이프라인 스크립트, 실험 코드
  docs/                      ML 처리 과정과 handoff 관련 문서

model_handoff/
  heatgrid_ml_models_2026-06-25/
                              모델 파일 중심 전달 패키지

inference_handoff/
  heatgrid_inference_package_2026-06-26/
                              운영 연동용 추론 패키지

report/
  experiment_comparison/     실험 비교 리포트와 성능 지표

diary/
  작업 기록과 인수인계 메모
```

## 환경 설정

프로젝트 기준 Python 버전은 3.12이며, 기본 패키지 관리는 `uv`를 사용합니다.

```powershell
uv sync
```

추론 패키지만 별도로 확인할 경우에는 아래처럼 설치할 수 있습니다.

```powershell
cd inference_handoff/heatgrid_inference_package_2026-06-26
pip install -e .
```

## 공식 파이프라인 스크립트

현재 기준으로 최종 모델 산출에 직접 연결되는 주요 스크립트는 아래와 같습니다.

```powershell
python PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
python PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
python PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py
```

이 스크립트들은 `data/processed/` 아래의 전처리 산출물을 사용해 위험도 모델, 리드타임 모델, 우선순위 산정 결과를 생성하거나 갱신합니다.

## 모델 Handoff

`model_handoff/heatgrid_ml_models_2026-06-25/`는 학습 완료된 모델과 메타데이터를 모아둔 폴더입니다.

```text
anomaly/
  standard_scaler.joblib
  isolation_forest.joblib
  baseline_model_metadata.json

risk/
  lightgbm_risk_model.joblib
  risk_model_group_calibration.json
  risk_model_metadata.json

leadtime/
  lightgbm_leadtime_bucket_model_promoted.joblib
  leadtime_bucket_model_promoted_metadata.json

priority/
  priority_engine_tuned_metadata.json

docs/
  agent_preprocessed_input_columns.md
  agent_full_data_contract.md

MANIFEST.json
```

이 폴더의 `joblib` 파일은 현재 프로젝트에서 생성된 모델 산출물과 SHA256 해시 기준으로 동일함을 확인했습니다.

다만 이 폴더에는 운영 데이터에서 모델 입력 피처를 만드는 전체 코드가 포함되어 있지 않습니다. 따라서 실제 서비스나 다른 프로젝트에 바로 붙일 때는 아래의 `inference_handoff`를 사용하는 것이 맞습니다.

## 추론 Handoff

`inference_handoff/heatgrid_inference_package_2026-06-26/`는 운영 프로젝트에 넘기기 위한 추론 패키지입니다.

포함 내용은 다음과 같습니다.

- 최종 모델 파일
- 모델 메타데이터
- 피처 컬럼 계약
- 결측치 보정 값
- 카테고리 one-hot 매핑
- 원천 운영 CSV를 6시간 윈도우 피처로 변환하는 코드
- 이상 탐지, 위험도, 리드타임, 우선순위 스코어링 코드
- CLI 실행 진입점
- 파일 무결성 확인용 SHA256 manifest

도움말 확인:

```powershell
python inference_handoff/heatgrid_inference_package_2026-06-26/run_inference.py --help
```

원천 운영 파일 하나를 바로 스코어링:

```powershell
python inference_handoff/heatgrid_inference_package_2026-06-26/run_inference.py score-raw-file `
  --input "data/raw_data/predist_v2/manufacturer 1/operational_data/substation_1.csv" `
  --raw-root "data/raw_data/predist_v2" `
  --output "scores.csv"
```

이미 생성된 윈도우 피처 CSV를 스코어링:

```powershell
python inference_handoff/heatgrid_inference_package_2026-06-26/run_inference.py score-windowed `
  --input "data/processed/ml_features/trainable_windows.csv" `
  --output "scores.csv"
```

## 재학습 범위

`inference_handoff`는 운영 추론용 패키지이며, 재학습 전체를 재현하기 위한 패키지는 아닙니다.

재학습이나 실험 감사까지 넘겨야 한다면 전체 저장소와 필요한 원천/전처리 데이터를 함께 제공해야 합니다. 이 경우 대상 팀에는 아래 항목이 필요합니다.

- 원천 데이터
- 라벨과 설비 메타데이터 정렬 로직
- 6시간 윈도우 전처리 로직
- 피처 선택 및 결측치 보정 계약 생성 과정
- train, validation, holdout 분리 정책
- 학습 스크립트 또는 노트북
- 실험 비교 결과
- 최종 모델 승격 기준과 기록

운영 추론과 재학습 범위의 차이는 아래 문서에 정리되어 있습니다.

```text
inference_handoff/heatgrid_inference_package_2026-06-26/docs/retraining_scope.md
```

## 검증 명령

추론 패키지 문법 확인:

```powershell
python -m compileall inference_handoff/heatgrid_inference_package_2026-06-26/src
```

원천 운영 파일 기준 smoke test:

```powershell
python inference_handoff/heatgrid_inference_package_2026-06-26/run_inference.py score-raw-file `
  --input "data/raw_data/predist_v2/manufacturer 1/operational_data/substation_1.csv" `
  --raw-root "data/raw_data/predist_v2" `
  --output "inference_handoff/heatgrid_inference_package_2026-06-26/examples/scores_from_raw_file_smoke.csv"
```

윈도우 피처 CSV 기준 smoke test:

```powershell
python inference_handoff/heatgrid_inference_package_2026-06-26/run_inference.py score-windowed `
  --input "data/processed/ml_features/trainable_windows.csv" `
  --output "inference_handoff/heatgrid_inference_package_2026-06-26/examples/scores_from_windowed_smoke.csv"
```

외부 전달 전에는 smoke test로 생성한 CSV가 패키지 안에 남아 있지 않은지 확인합니다.

## 참고 사항

- `report/`와 `PREPROCESSING/osj/experiments/06_test/`는 실험 비교와 분석용입니다.
- `data/processed/`는 생성 산출물을 포함하므로 용량이 커질 수 있습니다.
- 우선순위 산정은 별도 `joblib` 모델이 아니라 `priority_engine_tuned_metadata.json` 기준의 규칙 기반 엔진입니다.
- 운영 프로젝트에 붙일 때는 `model_handoff`만 넘기지 말고 `inference_handoff/heatgrid_inference_package_2026-06-26/`를 기준으로 전달하는 것이 안전합니다.
