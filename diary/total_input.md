# HeatGrid Agent 프로젝트 전체 입력 정리

이 문서는 새 Codex 세션이나 다른 작업자가 HeatGrid Agent 프로젝트의 전체 구조를 빠르게 이해하도록 정리한 개요 문서다.

## 프로젝트 이름

**HeatGrid Agent**

이전 대화 중 `HeatGrid Copilot`이라는 표현이 있었지만, 현재 프로젝트명은 **HeatGrid Agent**로 정리한다.

## 프로젝트 목적

HeatGrid Agent는 지역난방 기계실 운영 데이터를 기반으로 이상징후를 탐지하고, 고장신고 전 위험 가능성을 분석하여 Agent가 점검 판단과 작업 문서 생성을 지원하는 시스템이다.

핵심은 고장을 확정하는 것이 아니다.

목표는 다음과 같다.

```text
운영 시계열 데이터 수집
→ 전처리 및 ML 입력 데이터 생성
→ 이상점수 및 위험 가능성 산출
→ Agent가 이력, 설비 구성, 센서 의미를 함께 해석
→ 점검 필요성, 원인 후보, 점검 항목 정리
→ 작업지시서 초안 작성
→ 운영자 검토 후 전달 여부 결정
```

중요한 역할 구분은 다음과 같다.

```text
ML은 위험 가능성과 분석 자료를 만든다.
Agent는 그 자료와 이력을 종합해서 현장 점검 업무로 연결한다.
```

## 이 프로젝트가 하는 일

- 지역난방 기계실 센서 시계열 데이터 분석
- 정상 패턴 대비 이상징후 탐지
- 고장신고 전 위험 가능성이 있는 구간 탐색
- 기계실별 위험 가능성 산출
- 고장신고까지 남은 lead time 후보 계산
- 주요 변화 센서 후보 추출
- 정비/작업 이력과의 관계 표시
- 설비 구성 유형 반영
- Agent가 판단할 수 있는 ML 산출물 생성
- Agent가 판단 근거, 원인 후보, 점검 항목, 작업지시서 초안을 작성

## 이 프로젝트가 하지 않는 일

- 고장 여부 확정
- 정확한 고장 발생 시점 예측
- 실제 설비 자동제어
- 자동 출동 지시
- 운영자 검토 없는 자동 메일 발송
- 열수송관 누수 위치 확정
- 전체 지역난방망 최적화

## 핵심 데이터

프로토타입의 핵심 데이터는 **PreDist v2**다.

현재 raw data 위치:

```text
data/raw_data/predist_v2/
```

구성:

```text
manufacturer 1/
manufacturer 2/
```

각 manufacturer 폴더에는 다음 파일들이 있다.

```text
operational_data/substation_*.csv
faults.csv
disturbances.csv
normal_events.csv
feature_descriptions.csv
configuration_types.csv
```

각 파일의 의미:

- `operational_data/substation_*.csv`
  - 기계실별 운영 센서 시계열
  - ML 입력의 핵심

- `faults.csv`
  - 고장신고 이력
  - 고장신고 전 위험 구간과 lead time 계산에 사용

- `disturbances.csv`
  - 정비/작업 이력
  - 이상징후가 실제 고장 가능성인지, 작업 영향인지 Agent가 해석할 때 사용

- `normal_events.csv`
  - 정상 이벤트 구간
  - 정상 학습 후보로 사용

- `feature_descriptions.csv`
  - 센서/변수 설명과 단위
  - Agent가 센서 의미를 설명할 때 사용

- `configuration_types.csv`
  - 기계실 설비 구성 유형
  - 예: SH, SH + DHW, buffer tank 포함 여부 등
  - 같은 센서 이상도 설비 구성에 따라 의미가 달라질 수 있음

## 데이터 관리 원칙

데이터 파일은 GitHub에 올리지 않는다.

`.gitignore` 대상:

```text
data/raw_data/
data/_downloads/
data/processed/
```

즉, raw data와 processed data는 로컬에서 생성하고 사용한다.
Git에는 노트북, 문서, 코드만 올린다.

## 전체 시스템 구성

프로젝트는 크게 다음 모듈로 나눈다.

```text
Data / Preprocessing
ML
Agent
Server
Frontend
DB
```

## 1. Data / Preprocessing

역할:

- 외부 데이터 다운로드
- raw data 구조 확인
- 라벨 구간 정렬
- ML 학습용 window dataset 생성
- feature 후보 정리

현재 위치:

```text
PREPROCESSING/osj/
PREPROCESSING/docs/
```

현재까지 만든 흐름:

```text
00_load_dataset.ipynb
→ 01_raw_inspection.ipynb
→ 02_label_alignment.ipynb
→ 03_preprocess_windows.ipynb
→ 04_feature_selection.ipynb
→ 05_baseline_anomaly_model.ipynb
```

## 2. ML

사용자가 담당하는 범위다.

ML 파트의 목표는 Agent에게 바로 판단 가능한 자료를 주는 것이다.
ML이 우선순위를 직접 결정하는 것이 아니다.

ML이 만들어야 할 산출물:

- 기계실 ID
- 시간 구간
- 예측/분석 대상 window
- 정상 후보 / 고장 전 위험 후보
- 이상점수
- 위험 가능성 점수
- confidence
- severity 후보
- 고장 라벨 후보
- 고장신고까지 남은 lead time
- 주요 변화 센서
- 데이터 품질 정보
- 정비/작업 관련 여부
- 설비 구성 정보

Agent에게 넘길 최종 형태는 대략 다음과 같다.

```json
{
  "substation_id": 10,
  "window_start": "2020-01-01 00:00:00",
  "window_end": "2020-01-01 06:00:00",
  "prediction_label": "pre_fault",
  "anomaly_score": 0.82,
  "risk_score": 0.76,
  "confidence": 0.91,
  "severity": "high",
  "fault_label": "pump failure",
  "estimated_lead_time_hours": 24,
  "main_abnormal_sensors": [
    "s_hc1_supply_temperature",
    "p_net_meter_flow"
  ],
  "data_quality_issue": false,
  "maintenance_related": false,
  "configuration_type": "SH + DHW"
}
```

## ML에서 중요한 관점

### 고장을 확정하지 않는다

ML 결과는 다음처럼 표현해야 한다.

좋은 표현:

```text
고장 전 위험 가능성이 높음
고장신고 전 구간과 유사한 패턴
점검 필요성이 있는 후보 구간
```

피해야 할 표현:

```text
고장 확정
몇 시간 뒤 고장 발생
자동 출동 필요
```

### 이상치는 제거하지 않는다

이상치는 고장 전 위험 징후일 수 있다.

따라서 이상치는 삭제하지 않고 다음처럼 다룬다.

```text
센서 오류 후보
급격한 변화 후보
실제 이상징후 후보
```

### 결측치는 처리하되 정보는 남긴다

결측값은 모델 입력을 위해 보간할 수 있다.
하지만 결측 정보는 feature로 남겨야 한다.

예:

```text
missing_count
missing_rate
data_quality_issue
```

### label leakage를 막는다

고장신고 이후 데이터가 고장 전 위험 학습에 들어가면 안 된다.

기준:

```text
window_end <= report_date
```

고장신고 이후가 섞일 수 있는 구간은 `post_fault_blocked`로 표시하고 학습에서 제외한다.

## 현재 ML 전처리 흐름

### 00. 데이터 다운로드

파일:

```text
PREPROCESSING/osj/00_load_dataset.ipynb
PREPROCESSING/docs/00_load_dataset.md
```

역할:

- Zenodo / Mendeley에서 ZIP 파일 다운로드
- 압축 해제
- `data/raw_data` 아래에 저장

### 01. raw 데이터 구조 확인

파일:

```text
PREPROCESSING/osj/01_raw_inspection.ipynb
PREPROCESSING/docs/01_raw_inspection.md
```

역할:

- 전체 운영 CSV 파일 수 확인
- 제조사별 컬럼 구조 확인
- 결측 행 수 / 결측률 확인
- label 파일 구조 확인

### 02. 라벨 구간 정렬

파일:

```text
PREPROCESSING/osj/02_label_alignment.ipynb
PREPROCESSING/docs/02_label_alignment.md
```

역할:

- `faults.csv`, `normal_events.csv`, `disturbances.csv`를 운영 시계열과 시간 기준으로 맞춤
- usable 라벨 구간 선별

산출물:

```text
data/processed/label_alignment/operational_coverage.csv
data/processed/label_alignment/fault_alignment.csv
data/processed/label_alignment/normal_alignment.csv
data/processed/label_alignment/disturbance_alignment.csv
```

중요 기준:

```text
fault window는 Report date 이후로 넘어가지 않는다.
fallback은 Report date - 3일 ~ Report date 기준이다.
```

### 03. ML 학습용 window dataset 생성

파일:

```text
PREPROCESSING/osj/03_preprocess_windows.ipynb
PREPROCESSING/docs/03_preprocess_windows.md
```

역할:

- 운영 시계열을 6시간 window로 변환
- 센서별 통계 feature 생성
- 결측/품질 feature 생성
- fault / normal / disturbance 정보 연결
- 설비 구성 정보 연결
- 학습 가능 여부 표시

산출물:

```text
data/processed/ml_windows/ml_window_dataset.csv
```

현재 검증 결과:

```text
행 수: 3,270
컬럼 수: 195

normal: 1,818
pre_fault: 815
unlabeled: 637

use_for_supervised_training True: 2,633
use_for_supervised_training False: 637
```

## 현재 추가 완료: 04 feature selection

04번은 현재 추가되어 있다.

파일:

```text
PREPROCESSING/osj/04_feature_selection.ipynb
PREPROCESSING/docs/04_feature_selection.md
```

목표:

```text
03번 window dataset에서 실제 ML 학습에 사용할 행과 컬럼을 확정한다.
```

04번에서 반영한 기준:

- `use_for_supervised_training == True`
- `normal`, `pre_fault` 라벨만 사용
- 기본 strict 학습셋은 `data_quality_issue == False`
- feature 선택 통계는 strict train split 기준
- 결측 대체값은 strict train split 기준
- strict / relaxed 입력을 모두 저장

04번 산출물:

```text
data/processed/ml_features/trainable_windows.csv
data/processed/ml_features/feature_columns.csv
data/processed/ml_features/metadata_columns.csv
data/processed/ml_features/imputation_values.csv
```

## 현재 추가 완료: 05 baseline anomaly model

05번도 현재 추가되어 있다.

파일:

```text
PREPROCESSING/osj/05_baseline_anomaly_model.ipynb
PREPROCESSING/docs/05_baseline_anomaly_model.md
```

역할:

- 04번 산출물을 받아 baseline 이상탐지 모델을 학습한다.
- `split_time_based == train`, `label == normal` 행만 모델 학습에 사용한다.
- IsolationForest 기반 anomaly baseline을 만든다.
- `split_time_based`, `split_substation_based` 기준 성능을 저장한다.
- threshold sweep과 모델/스케일러 파일을 저장한다.

05번 산출물:

```text
data/processed/ml_baseline/anomaly_baseline_scores.csv
data/processed/ml_baseline/anomaly_baseline_metrics.csv
data/processed/ml_baseline/anomaly_baseline_thresholds.csv
data/processed/ml_baseline/anomaly_baseline_threshold_sweep_metrics.csv
data/processed/ml_baseline/models/
```

## 이후 ML 단계 제안

전체 ML 노트북 흐름은 다음처럼 가면 된다.

```text
00_load_dataset
01_raw_inspection
02_label_alignment
03_preprocess_windows
04_feature_selection
05_baseline_anomaly_model
06_risk_leadtime_model
07_explainability
08_export_for_agent
```

### 05. baseline model

모델:

- IsolationForest
  - 정상 패턴 대비 이상점수 산출
  - 06번 LightGBM 입력으로 사용할 `anomaly_score` 저장

### 06. risk and lead-time model

- LightGBM
  - `normal` vs `pre_fault` 분류
  - 고장신고 전 위험구간과 유사한지 판단
  - `risk_score` 또는 `risk_probability` 산출

### 06 audit companion

- holdout normal과 pre_fault 분포 차이 진단
- 제조사 / 기계실 / fault event 기준 false positive 집중 구간 확인
- holdout feature drift 점검

초기에는 복잡한 딥러닝보다 baseline 모델을 먼저 만든다.

### 06번에서 함께 확인할 평가 항목

확인할 것:

- label별 성능
- lead time 구간별 성능
- data_quality_issue 포함/제외 성능
- manufacturer별 성능
- substation 기반 holdout 성능
- event 기반 holdout 성능

2026-06-24 기준 06번 LightGBM baseline을 추가했다.

생성 파일:

```text
PREPROCESSING/osj/06_risk_leadtime_model.ipynb
PREPROCESSING/docs/06_risk_leadtime_model.md
data/processed/ml_risk/lgbm_risk_scores.csv
data/processed/ml_risk/lgbm_risk_metrics.csv
data/processed/ml_risk/lgbm_risk_thresholds.csv
data/processed/ml_risk/lgbm_feature_importance.csv
data/processed/ml_risk/event_split_leakage_audit.csv
data/processed/ml_risk/models/lightgbm_risk_model.joblib
data/processed/ml_risk/models/risk_model_metadata.json
```

현재 06번은 `split_event_based` 기준 baseline으로 완료했다.
event split에서는 fault event cross-split이 0개지만, 기존 time/substation split에는 audit 용도로 leakage가 남아 있다.
이후 06 보강으로 `anomaly_label`과 누적 계량기 절대값 proxy feature를 제거하고 LightGBM 복잡도를 줄였다.
event validation F1 기준 threshold selection 결과는 `data/processed/ml_risk/lgbm_threshold_selection.csv`에 저장했다.
보강 후 모델 버전은 `lgbm_risk_06_guarded_v1`이다.
holdout 붕괴 원인 진단 산출물을 추가했다.

```text
data/processed/ml_risk/holdout_split_label_diagnostics.csv
data/processed/ml_risk/holdout_error_diagnostics.csv
data/processed/ml_risk/holdout_feature_drift_diagnostics.csv
```

진단상 holdout normal, 특히 manufacturer 2 normal의 risk가 높아 false positive가 많이 발생한다.

### 07. Agent handoff output

Agent에게 넘길 형태로 결과를 정리한다.

산출물 후보:

```text
data/processed/agent_handoff/ml_agent_handoff.csv
data/processed/agent_handoff/ml_agent_handoff.jsonl
```

포함해야 할 정보:

- substation_id
- window_start
- window_end
- prediction_label
- anomaly_score
- risk_score
- confidence
- severity
- fault_label 후보
- estimated_lead_time_hours
- main_abnormal_sensors
- data_quality_issue
- maintenance_related
- configuration_type
- model_version

## Agent 파트 개요

Agent는 ML 결과를 그대로 나열하지 않는다.

Agent가 종합할 정보:

- ML 이상점수
- 위험 가능성 점수
- lead time
- 주요 변화 센서
- fault 이력
- disturbance 이력
- feature description
- configuration type
- 데이터 품질

Agent 결과에는 다음이 포함되어야 한다.

- 우선 점검 대상 판단
- 판단 근거
- 원인 후보
- 주요 이상 센서
- 점검 항목
- 한계 설명
- 작업지시서 초안

Agent는 자동 발송하지 않는다.
운영자 검토 단계를 반드시 둔다.

## Server 파트 개요

Server는 FastAPI 기반으로 구성할 계획이다.

역할:

- DB, ML, Agent, Frontend 연결
- 기계실 목록 조회
- 센서 시계열 조회
- ML 결과 조회
- Agent 결과 조회
- 작업지시서 저장 및 조회
- 운영자 확인 후 메일 발송 요청 처리
- 발송 이력 저장

## Frontend 파트 개요

Frontend는 React + Vite 기반 대시보드로 구성할 계획이다.

필수 화면:

- 전체 기계실 상태 요약
- 기계실별 위험 가능성 및 우선 점검 후보
- 선택 기계실의 센서 시계열 그래프
- P&ID 또는 계통도 기반 이상 센서 위치 표시
- Agent 판단 결과 패널
- 작업지시서 초안 검토 화면
- 운영자 확인 후 전달 여부 선택
- 발송 이력 확인

## DB 파트 개요

PostgreSQL + TimescaleDB 사용을 기준으로 한다.

예상 테이블:

```text
substations
sensor_timeseries
fault_reports
maintenance_logs
configuration_types
ml_results
agent_results
work_orders
mail_logs
```

## 개발 원칙

- 처음부터 완성형 서비스를 만들지 않는다.
- 작은 단위로 동작 확인 후 확장한다.
- 데이터 로딩, 전처리, ML, Agent, Server, Frontend를 모듈 단위로 분리한다.
- 고장 확정 표현을 쓰지 않는다.
- 자동 제어, 자동 출동, 자동 발송 기능은 구현하지 않는다.
- 운영자 검토 단계를 반드시 포함한다.
- Agent 결과는 근거, 원인 후보, 점검 항목, 한계 설명을 포함해야 한다.
- PreDist 데이터 구조를 임의로 가정하지 않고 실제 파일과 컬럼을 확인한다.
- 변수명과 함수명은 영어를 사용한다.
- 설명, README, 문서는 한국어 중심으로 작성한다.
- 사용자에게 보이는 표 제목과 컬럼명은 한글로 표시한다.

## 새 세션에서 가장 먼저 볼 파일

새 Codex 세션에서는 다음 파일을 먼저 보면 된다.

```text
diary/total_input.md
diary/2026-06-23_ml_preprocessing_diary.md
PREPROCESSING/docs/03_preprocess_windows.md
PREPROCESSING/osj/03_preprocess_windows.ipynb
```

그 다음 04번 작업을 시작하면 된다.
