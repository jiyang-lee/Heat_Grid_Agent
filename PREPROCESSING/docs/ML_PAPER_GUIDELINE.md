# PreDist 논문 기반 ML 작업 가이드라인

참고 논문:

- *Enabling Predictive Maintenance in District Heating Substations: A Labelled Dataset and Fault Detection Evaluation Framework based on Service Data*
- arXiv v2: https://arxiv.org/html/2511.14791v2

이 문서는 위 논문을 기준으로, `HeatGrid Agent`의 ML 파트를 어떤 순서와 기준으로 구현해야 하는지 정리한다.

## 1. 이 논문에서 가져와야 하는 핵심 방향

이 논문의 핵심은 세 가지다.

1. 공개된 서비스 검증 기반 라벨 데이터셋을 사용한다.
2. 조기 고장탐지는 **정확도만이 아니라 신뢰성(reliability)과 조기성(earliness)** 을 함께 본다.
3. 탐지 결과는 **원인 설명(root-cause analysis)** 까지 연결되어야 한다.

즉, ML은 단순히 이상점수를 내는 것이 아니라 다음을 만족해야 한다.

- 정상 상태를 안정적으로 구분할 것
- 고장을 너무 늦게 잡지 않을 것
- 왜 이상으로 봤는지 근거를 줄 것

## 2. 우리 프로젝트에 맞는 해석

우리 시스템에서 ML은 최종 우선순위를 결정하지 않는다.

ML의 역할은 다음이다.

- 기계실별 시계열 패턴을 보고 이상 여부를 추정
- fault report 또는 maintenance event와 유사한 위험 신호를 추정
- Agent가 통합 판단할 수 있도록 리드타임과 근거를 제공

Agent의 역할은 다음이다.

- ML 출력, 설비 구성, 이력 정보를 결합
- 최종 점검 대상과 설명을 생성
- 작업지시서 초안 수준의 문맥을 만든다

## 3. 논문에서 유효한 구현 포인트

### 3.1 Isolation Forest 기반 이상탐지

논문은 normal behaviour model 기반 이상탐지 방향을 제시한다.
우리 프로젝트의 기본 구현은 `Isolation Forest`로 둔다.

핵심 아이디어는 다음과 같다.

- 정상 패턴으로 학습
- 정상 패턴과 다른 센서 조합을 고립시키기 쉬운 정도로 점수화
- anomaly score가 커지면 정상 운전 패턴에서 더 많이 벗어난 것으로 본다

이 방식은 우리 프로토에서도 baseline으로 쓰기 좋다.

권장 이유:

- 구조가 단순하다
- 라벨이 부족한 운영 시계열에 적용하기 쉽다
- 이상점수를 만들기 쉽다
- Agent에게 설명하기 쉽다

### 3.2 조건부 정보 사용

논문은 다음 조건부 변형도 비교한다.

- hour-of-day
- day-of-week
- day-of-year

이 뜻은 단순 센서값만 쓰지 말고, 시간 문맥을 feature로 넣으라는 의미다.

우리 프로젝트에서는 다음처럼 번역할 수 있다.

- 시간대
- 요일
- 계절성
- 난방 시즌 여부

이 정보는 리드타임과 이상 패턴 해석에 도움이 된다.

### 3.3 평가 기준

논문은 다음 세 가지를 중시한다.

- accuracy: 정상 상태를 얼마나 잘 맞추는가
- reliability: 이벤트 단위로 고장을 얼마나 믿을 만하게 잡는가
- earliness: 고장 신고보다 얼마나 일찍 잡는가

우리 프로젝트도 이 구조를 따라야 한다.

즉, 모델 성능은 “정확도 하나”로 끝내면 안 된다.

### 3.4 Root-cause analysis

논문은 ARCANA 같은 feature attribution을 사용해 원인 후보를 설명한다.

우리 프로젝트에서는 최소한 아래가 필요하다.

- 상위 기여 센서
- 이상 구간
- 센서별 점수
- 사람이 읽을 수 있는 설명

Agent는 이 설명을 받아 “왜 이 기계실을 먼저 봐야 하는지”를 정리한다.

## 4. 우리 ML 구현 가이드라인

### 4.1 첫 번째 목표

첫 목표는 멋진 모델이 아니라 **재현 가능한 baseline**이다.

권장 순서:

1. 데이터 로딩
2. 전처리
3. 윈도우 생성
4. Isolation Forest 기반 anomaly score
5. faults.csv 기준 고장신고 전 위험구간 라벨 생성
6. LightGBM 기반 risk score 또는 risk probability
7. event 단위 평가
8. feature attribution 또는 센서 중요도
9. Agent 전달용 출력 포맷 저장

### 4.2 데이터 선택

논문 기준으로 PreDist v2는 다음 구조를 활용한다.

- operational_data
- faults.csv
- disturbances.csv
- normal_events.csv
- feature_descriptions.csv
- configuration_types.csv

우리 구현에서는 다음 원칙을 따른다.

- `operational_data`를 주 입력으로 쓴다
- `faults.csv`로 fault 기준 구간을 만든다
- `disturbances.csv`로 최근 작업 영향 구간을 반영한다
- `normal_events.csv`로 정상 구간을 확보한다
- `configuration_types.csv`로 기계실 유형별 feature 차이를 반영한다

### 4.3 학습 샘플 구성

논문 취지에 맞게 샘플은 단순 개별 시점이 아니라 구간(window) 단위로 만든다.

권장 방식:

- 입력: 과거 N시간 또는 N포인트
- 출력: anomaly score, risk score, lead time 후보
- 부가정보: substation_id, manufacturer, config type, 시간대 feature

### 4.4 결과 계약

ML은 아래 정보를 반드시 반환해야 한다.

- `substation_id`
- `timestamp`
- `prediction_label`
- `anomaly_score` 또는 `confidence`
- `severity`
- `fault_label` 가능하면 추가
- `predicted_series`

권장 추가 항목:

- `lead_time_hours`
- `lead_time_bucket`
- `lead_time_confidence`
- `top_sensors`
- `sensor_scores`
- `window_start`
- `window_end`
- `model_version`
- `feature_version`
- `data_version`

## 5. 논문에서 가져온 평가 원칙

### 5.1 정상 이벤트 평가

정상 이벤트에서 false alarm이 너무 많으면 안 된다.

즉,

- 정상 데이터는 안정적으로 normal로 나와야 한다
- 운영자가 계속 무시하게 만들면 안 된다

### 5.2 fault 이벤트 평가

fault 이벤트에서는 다음을 본다.

- 실제 고장을 잡았는가
- 얼마나 빨리 잡았는가
- 얼마나 적은 false alarm으로 잡았는가

### 5.3 조기성

우리 시스템의 목적은 고장 확정이 아니라 **미리 점검할 수 있게 하는 것**이다.

따라서 리드타임은 중요하다.

권장 출력:

- `estimated_lead_time`
- `lead_time_hours`
- `lead_time_bucket`

## 6. 우리 프로젝트에 대한 실무 권고

### 6.1 모델 구성

처음부터 복잡하게 가지 말고 아래 순서로 간다.

1. rule-based baseline
2. Isolation Forest anomaly baseline
3. faults.csv 기준 위험구간 라벨 생성
4. LightGBM supervised risk baseline
5. eventwise evaluation
6. feature attribution

### 6.2 설명 가능성

Agent가 쓰려면 설명 가능성이 중요하다.

따라서 결과에는 최소한 다음이 있어야 한다.

- 어떤 센서가 중요했는지
- 어떤 구간이 이상했는지
- 왜 위험한지
- 얼마나 빨리 대응해야 하는지

### 6.3 우선순위는 ML이 직접 내지 않음

논문 취지와 우리 시스템 구조를 합치면,

- ML은 abnormality, risk, lead time, evidence를 준다
- Agent가 이 결과를 합쳐 점검 우선순위를 정한다

## 7. 실제 작업 순서

다음 순서로 구현하면 된다.

1. PreDist v2 raw data 로더 작성
2. substation별 window 생성
3. AE baseline 학습
4. anomaly score export
5. fault/normal event 기준 evaluation
6. lead time 추정 추가
7. sensor attribution 추가
8. Agent 전달 JSON 스펙 고정
9. 문서화 및 재현 스크립트 정리

## 8. 한 줄 결론

이 논문을 기준으로 하면, ML팀은 **정상/이상 판정, 위험도, 리드타임, 근거 센서, 시계열 예측값**을 제공하고, Agent가 이를 통합해 최종 판단을 내리는 구조로 가야 한다.
