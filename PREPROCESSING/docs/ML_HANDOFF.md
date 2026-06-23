# HeatGrid Agent ML 인수 문서

이 문서는 `HeatGrid Agent` 프로젝트에서 **ML 파트 담당자**가 구현해야 할 범위를 정리한 인수용 문서다.

목표는 `data/raw_data`의 원천 데이터를 읽어 전처리하고, 학습/추론 결과를 만들어서 **다음 단계 Agent 제작자가 바로 사용할 수 있는 형태**로 넘기는 것이다.

## 1. 현재 위치

현재 저장소에는 다음이 준비되어 있다.

- `data/raw_data/predist_v2/`
  - PreDist v2 원천 데이터
- `data/raw_data/xai4heat_scada_dataset/`
  - 보조 시계열 데이터
- `PREPROCESSING/00_load_dataset.ipynb`
  - 원천 데이터 다운로드 및 로컬 정리 노트북
- `PREPROCESSING/docs/00_load_dataset.md`
  - 위 노트북 설명서
- `.gitignore`
  - `data/raw_data/`, `data/_downloads/` Git 제외

즉, **데이터는 준비되어 있고 ML 본체는 아직 없는 상태**다.

## 2. ML 파트의 책임 범위

ML 담당자가 해야 할 일은 아래까지만이다.

1. raw data 로딩
2. 전처리
3. 학습 데이터 생성
4. 모델 학습
5. 추론 수행
6. 결과 저장
7. Agent 제작자가 읽을 수 있는 결과 계약 정의

ML 담당자가 하지 않는 일은 다음과 같다.

- Agent 판단 로직 작성
- 작업지시서 작성
- 메일 발송
- 운영자 승인 UI
- 자동제어

## 3. 입력 데이터 기준

### 3.1 PreDist v2

기본 입력은 PreDist v2다.

사용 파일:

- `operational_data/substation_*.csv`
- `faults.csv`
- `disturbances.csv`
- `normal_events.csv`
- `feature_descriptions.csv`
- `configuration_types.csv`

### 3.2 보조 데이터

필요하면 `xai4heat_scada_dataset`를 보조 실험용으로 사용할 수 있다.

다만 프로토 기준의 기본 데이터는 PreDist v2로 고정한다.

## 4. ML이 만들어야 할 산출물

Agent 제작자가 바로 쓸 수 있도록, ML 결과는 최소한 아래 항목을 포함해야 한다.

- `substation_id`
- `timestamp_start`
- `timestamp_end`
- `anomaly_score`
- `risk_score`
- `top_sensors`
- `fault_reference` 또는 관련 fault event id
- `maintenance_reference` 또는 관련 disturbance event id
- `model_version`
- `feature_version`
- `prediction_created_at`

예시 형태:

```json
{
  "substation_id": 12,
  "timestamp_start": "2026-06-23T00:00:00",
  "timestamp_end": "2026-06-23T01:00:00",
  "anomaly_score": 0.87,
  "risk_score": 0.73,
  "top_sensors": ["p_hc1_supply_temperature", "s_dhw_return_temperature"],
  "model_version": "iforest_v1",
  "feature_version": "feature_v1"
}
```

## 5. 권장 폴더 구조

ML 중심으로는 아래처럼 나누는 것이 가장 단순하다.

```text
src/
  heatgrid_copilot/
    ingestion/
    preprocessing/
    features/
    ml/
    evaluation/
    storage/
    schemas/
    utils/

data/
  raw_data/
  processed/
  features/
  results/
  cache/

tests/
docs/
PREPROCESSING/
```

### 폴더 역할

- `ingestion/`
  - raw data 로딩
  - 파일 위치, 파일 목록, substation 단위 읽기
- `preprocessing/`
  - 결측치 처리
  - 시간 정렬
  - 윈도잉
  - 라벨 매칭
- `features/`
  - ML 학습용 feature 생성
  - 집계 피처, 변화량 피처, 구간 피처
- `ml/`
  - 모델 학습
  - 추론
  - 모델 저장/로드
- `evaluation/`
  - 기본 성능 확인
  - 고장 전 위험구간에서의 정성 확인
- `storage/`
  - 결과 파일 저장
  - DB 적재 준비
- `schemas/`
  - input/output 데이터 계약
- `utils/`
  - 공통 함수

## 6. 구현해야 할 최소 기능

프로토 단계에서 먼저 구현할 것은 아래 순서다.

### 6.1 데이터 로딩

- substation 단위 파일 읽기
- manufacturer 1, 2 구분
- `faults.csv`, `disturbances.csv`, `normal_events.csv` 함께 로딩
- `feature_descriptions.csv`, `configuration_types.csv` 함께 로딩

### 6.2 전처리

- 컬럼명 정리
- datetime 파싱
- 중복 제거
- 결측치 처리 기준 정의
- 긴 결측 구간 분리
- 이상 구간과 정상 구간 분리

### 6.3 feature 생성

- window 기반 집계
- 이동평균 / 이동표준편차
- 변화량 / 차분
- 센서별 min / max / mean / median
- fault 근접 구간용 feature

### 6.4 baseline 모델

- IsolationForest 기반 anomaly score
- 간단한 분류/회귀 모델로 risk score 산출
- 초기에는 LightGBM 또는 대체 가능한 tree 기반 모델 사용

### 6.5 결과 저장

- parquet 또는 csv로 저장
- 필요하면 DB 적재용 스키마도 함께 정의
- Agent 제작자가 읽을 수 있는 JSON export 제공

## 7. 모델 선택 기준

프로토에서는 복잡한 모델보다 재현성과 설명 가능성을 우선한다.

권장 순서:

1. 규칙 기반 feature 생성
2. IsolationForest로 이상점수
3. LightGBM 또는 유사 모델로 위험도
4. feature importance 또는 top sensor 추출

처음부터 딥러닝으로 가지 않는다.

## 8. 결과 계약

ML 출력은 Agent가 읽기 쉬운 계약을 가져야 한다.

필수 원칙:

- substation 단위로 읽을 수 있어야 한다.
- 시간 구간이 명시되어야 한다.
- 점수 값의 의미가 문서화되어야 한다.
- top sensor가 있어야 한다.
- model version과 feature version이 있어야 한다.
- 후속 작업자가 DB든 파일이든 그대로 읽을 수 있어야 한다.

## 9. 개발 순서

다음 순서로 구현한다.

1. raw data loader
2. preprocessing pipeline
3. feature generator
4. baseline ML model
5. inference output schema
6. result storage
7. evaluation notebook or script
8. Agent 전달용 export format

## 10. 작업 규칙

- raw data는 Git에 올리지 않는다.
- 데이터 경로는 코드에 하드코딩하지 말고 설정으로 분리한다.
- ML과 Agent를 섞지 않는다.
- 결과 계약을 먼저 정하고 모델을 붙인다.
- 설명 가능한 baseline부터 만든다.
- README와 문서는 한국어 중심으로 유지한다.

## 11. 현재 상태 요약

지금 필요한 것은 다음이다.

- `src/heatgrid_copilot/` 골격 생성
- raw data loader 작성
- preprocessing 작성
- feature pipeline 작성
- ML baseline 작성
- 결과 export 포맷 정의

이 문서는 이후 작업자가 **Agent 전 단계에 넘길 ML 산출물**을 만들 때 기준 문서로 사용한다.
