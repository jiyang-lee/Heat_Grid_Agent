# 01. 원천 데이터 구조 확인 문서

이 문서는 `PREPROCESSING/osj/01_raw_inspection.ipynb`의 목적과 출력 기준을 HeatGrid Agent 프로젝트 관점에서 정리한다.

01번 노트북은 샘플 CSV 하나를 확인하는 단계가 아니다.
모든 운영 CSV를 기준으로 ML 입력 데이터의 규모, 컬럼 구조, 결측 품질을 확인한다.

## 프로젝트 관점의 목적

HeatGrid Agent에서 ML은 기계실별 이상점수, 위험 가능성, lead time, 주요 이상 센서 후보를 Agent에게 제공해야 한다.
이를 위해 01번 단계에서는 어떤 센서 컬럼을 공통 feature로 쓸 수 있는지, 어떤 컬럼은 제조사별로 따로 처리해야 하는지, 결측이 모델 입력에 영향을 줄 정도인지 확인한다.

## 확인하는 것

### 1. 운영 시계열 파일 규모

- manufacturer별 운영 CSV 파일 수
- 파일별 행 수
- 파일별 컬럼 수
- 파일별 결측 포함 행 수
- 파일별 timestamp 최소/최대 시각

### 2. 전체 파일 기준 컬럼 구조

- 원본 컬럼명
- 사용자 표시용 한글 컬럼명
- manufacturer별 전체 파일 사용 여부
- 공통 feature 후보
- manufacturer 2 전용 컬럼

### 3. 전체 파일 기준 결측치

- 컬럼별 전체 행 수
- 컬럼별 결측 행 수
- 컬럼별 결측률

결측치는 그래프로 보지 않는다.
전처리 기준에는 숫자 표가 더 직접적이므로 숫자 요약만 남긴다.

### 4. 라벨 파일 구조

- `faults.csv`: 고장 신고 전 위험 구간 후보
- `normal_events.csv`: 정상 패턴 기준 구간
- `disturbances.csv`: 정비/작업 영향 확인용 이력
- `feature_descriptions.csv`: Agent 설명에 사용할 센서 의미 사전
- `configuration_types.csv`: 설비 구성별 해석 기준

## 다음 단계 연결

01번에서 확인한 전체 파일 기준 컬럼 구조와 결측 요약을 바탕으로 `02_label_alignment.ipynb`에서 fault / normal / disturbance 이벤트를 실제 운영 시계열 시간축에 맞춘다.
