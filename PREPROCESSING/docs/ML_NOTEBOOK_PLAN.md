# ML 노트북 구성 및 작업 계획

이 문서는 `HeatGrid Agent` 프로젝트에서 ML 파트를 **노트북 단위로 분리**해서 진행하기 위한 계획서다.

목표는 다음과 같다.

- `raw_data`를 안정적으로 읽는다.
- 전처리부터 feature 생성, 모델 학습, 평가, 시각화, 결과 export까지 단계별로 분리한다.
- 각 단계마다 `01`, `02`, `03`처럼 번호를 붙여 순서를 명확히 한다.
- 각 노트북에 대응하는 `docs` 문서를 함께 쌓는다.

---

## 1. 전체 진행 원칙

### 1.1 노트북은 한 번에 하나의 책임만 가진다

각 노트북은 아래처럼 한 가지 목적만 담당한다.

- 데이터 확인
- 전처리
- feature 생성
- baseline 학습
- 평가
- 시각화
- 결과 export

한 노트북에 너무 많은 기능을 넣지 않는다.

### 1.2 문서는 노트북과 같이 쌓는다

각 노트북에는 대응하는 설명 문서를 둔다.

예:

- `01_raw_inspection.ipynb`
- `docs/01_raw_inspection.md`

이렇게 하면 다음 작업자가 번호만 보고 흐름을 따라갈 수 있다.

### 1.3 번호는 실행 순서다

파일명 앞 숫자는 단순 정렬이 아니라 **작업 순서**다.

따라서 중간에 새 단계가 생기면 번호를 억지로 끼워 넣기보다, 다음 번호를 사용한다.

---

## 2. 권장 노트북 흐름

아래 순서로 진행하는 것을 권장한다.

### 00. 데이터 다운로드 및 정리

- 파일: `PREPROCESSING/00_load_dataset.ipynb`
- 문서: `PREPROCESSING/docs/00_load_dataset.md`

역할:

- 원천 데이터를 로컬에 받는다.
- `data/raw_data` 아래에 정리한다.

현재 완료된 단계다.

### 01. 원천 데이터 구조 확인

- 파일: `PREPROCESSING/01_raw_inspection.ipynb`
- 문서: `PREPROCESSING/docs/01_raw_inspection.md`

목적:

- manufacturer 1, 2의 CSV 구조 확인
- 컬럼명, dtype, 결측치, 중복, timestamp 형식 확인
- `faults.csv`, `disturbances.csv`, `normal_events.csv`의 기본 구조 확인

핵심 출력:

- 각 파일의 컬럼 목록
- 샘플 행
- 결측치 요약
- 시간 범위

시각화:

- 변수별 결측치 막대 그래프
- timestamp 분포
- substation별 row count

### 02. 라벨과 이력 정리

- 파일: `PREPROCESSING/02_label_alignment.ipynb`
- 문서: `PREPROCESSING/docs/02_label_alignment.md`

목적:

- `faults.csv`, `disturbances.csv`, `normal_events.csv`를 기준으로 이벤트 타임라인 정리
- fault, disturbance, normal event의 시간 관계를 보기 쉽게 만든다
- 학습/평가용 구간을 정의한다

핵심 출력:

- event timeline 테이블
- fault window 후보
- normal window 후보

시각화:

- 기계실별 이벤트 타임라인
- fault vs disturbance vs normal 구간 비교

### 03. 전처리 및 윈도우 생성

- 파일: `PREPROCESSING/03_preprocessing_windows.ipynb`
- 문서: `PREPROCESSING/docs/03_preprocessing_windows.md`

목적:

- 결측치 처리
- timestamp 정렬
- 이상치와 불완전 구간 처리
- sliding window 생성

핵심 출력:

- windowed dataset
- train / validation / test split 후보

시각화:

- 원시 시계열 vs 전처리 후 시계열
- window 분할 시각화
- 결측 구간 전후 비교

### 04. feature 생성

- 파일: `PREPROCESSING/04_feature_engineering.ipynb`
- 문서: `PREPROCESSING/docs/04_feature_engineering.md`

목적:

- 센서 집계 feature 생성
- 변화량 feature 생성
- 시간 문맥 feature 생성
- configuration type 반영 feature 생성

핵심 출력:

- feature table
- feature list
- feature version 정의

시각화:

- feature correlation
- feature distribution
- 상위 feature 중요도 후보

### 05. baseline 이상탐지 모델

- 파일: `PREPROCESSING/05_baseline_anomaly_model.ipynb`
- 문서: `PREPROCESSING/docs/05_baseline_anomaly_model.md`

목적:

- normal behaviour model baseline 구축
- anomaly score 산출
- AE 또는 IsolationForest baseline 비교

핵심 출력:

- anomaly score
- reconstruction error 또는 이상점수
- threshold 후보

시각화:

- 정상 vs 이상 score 분포
- reconstruction error curve
- threshold line 포함 분포 그래프

### 06. 위험도 및 리드타임 추정

- 파일: `PREPROCESSING/06_risk_leadtime_model.ipynb`
- 문서: `PREPROCESSING/docs/06_risk_leadtime_model.md`

목적:

- fault/maintenance 이력과의 유사도를 기반으로 위험도 추정
- 이벤트까지의 남은 시간 또는 리드타임 구간 추정

핵심 출력:

- risk score
- risk class
- lead time estimate
- confidence

시각화:

- 리드타임 분포
- risk score와 fault event 관계
- 예측 시점 대비 실제 fault 시점 비교

### 07. 근거 설명 및 센서 중요도

- 파일: `PREPROCESSING/07_explainability.ipynb`
- 문서: `PREPROCESSING/docs/07_explainability.md`

목적:

- 어떤 센서가 이상 판단에 기여했는지 정리
- Agent가 읽을 수 있는 형태로 근거를 만든다

핵심 출력:

- top_sensors
- sensor_scores
- 이상 구간 설명

시각화:

- sensor importance bar plot
- time segment highlight
- 기계실별 설명 요약

### 08. Agent 전달용 export

- 파일: `PREPROCESSING/08_export_for_agent.ipynb`
- 문서: `PREPROCESSING/docs/08_export_for_agent.md`

목적:

- ML 결과를 Agent가 바로 읽을 수 있는 JSON/CSV/Parquet로 저장
- 계약 스키마를 고정

핵심 출력:

- `substation_id`
- `timestamp`
- `prediction_label`
- `anomaly_score`
- `confidence`
- `severity`
- `fault_label`
- `predicted_series`
- `lead_time_hours`
- `top_sensors`

시각화:

- export 결과 샘플 확인
- substation별 결과 요약 테이블

---

## 3. 문서 누적 방식

각 노트북마다 아래 형식의 문서를 만든다.

- 목적
- 입력 데이터
- 전처리 또는 분석 절차
- 주요 산출물
- 시각화 설명
- 다음 단계로 넘길 내용

문서 파일명 규칙:

- `docs/01_raw_inspection.md`
- `docs/02_label_alignment.md`
- `docs/03_preprocessing_windows.md`
- `docs/04_feature_engineering.md`
- `docs/05_baseline_anomaly_model.md`
- `docs/06_risk_leadtime_model.md`
- `docs/07_explainability.md`
- `docs/08_export_for_agent.md`

---

## 4. 시각화 방안

시각화는 단순 예쁜 그림이 아니라 **다음 단계 판단을 돕는 근거**로 사용한다.

### 4.1 원천 데이터 확인 시각화

- 시계열 라인 플롯
- 결측치 히트맵
- substation별 데이터 길이 분포

### 4.2 라벨 확인 시각화

- fault event timeline
- disturbance overlap
- normal event range

### 4.3 모델 결과 시각화

- anomaly score curve
- threshold overlay
- fault report 시점 대비 예측 시점 비교

### 4.4 해석 시각화

- top sensor bar chart
- window별 score heatmap
- 기계실별 위험 구간 비교

### 4.5 Agent 전달 시각화

- 기계실별 요약 카드 형태 표
- `substation_id`별 최근 상태 표
- lead time과 severity를 함께 보여주는 요약표

---

## 5. 추천 작업 순서

실제 작업은 아래 순서로 진행하는 것이 좋다.

1. `00_load_dataset.ipynb` 유지
2. `01_raw_inspection.ipynb`
3. `02_label_alignment.ipynb`
4. `03_preprocessing_windows.ipynb`
5. `04_feature_engineering.ipynb`
6. `05_baseline_anomaly_model.ipynb`
7. `06_risk_leadtime_model.ipynb`
8. `07_explainability.ipynb`
9. `08_export_for_agent.ipynb`

각 단계가 끝날 때마다 대응하는 `docs/` 문서를 추가한다.

---

## 6. 최종 목표

이 흐름의 최종 목표는 다음이다.

- raw data를 안정적으로 읽는다.
- ML이 anomaly, risk, lead time, evidence를 만든다.
- Agent가 이 결과를 받아 최종 판단한다.
- 후속 작업자가 노트북 번호만 따라가도 전체 흐름을 재현할 수 있다.
