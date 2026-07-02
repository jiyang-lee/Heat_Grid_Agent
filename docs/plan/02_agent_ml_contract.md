# Agent - ML 출력 계약 초안

## 1. 목적

이 문서는 ML 팀이 2일 내에 만들어 올 예측 결과를 Agent 쪽이 안정적으로 받기 위한 계약 초안이다.

ML 모델의 최종 출력이 아직 완전히 정해지지 않았으므로, Agent는 출력 형태를 직접 가정하지 않고 canonical schema를 둔다.

## 2. 왜 계약이 필요한가

- ML 출력이 바뀌어도 Agent가 바로 깨지지 않아야 한다.
- raw 센서 입력이 그대로 들어올 수 있다.
- 예측 결과와 최종 판단은 같은 데이터가 아니다.
- 전처리와 판단을 같은 단계에서 처리하면 나중에 확장하기 어렵다.

## 3. canonical prediction schema

Agent는 ML 출력 원본을 그대로 쓰지 않고, `한 건의 prediction event + optional time window` 형태로 감싼다.

### 3.1 고정 코어 필드

- `prediction_id`
- `event_id`
- `source_type`
- `source_dataset`
- `schema_version`
- `substation_id`
- `observed_at`
- `prediction_label`
- `prediction_type`
- `prediction_score` 또는 `confidence`

### 3.2 확장 가능 필드

- `site_id`
- `asset_id`
- `window_start`
- `window_end`
- `severity`
- `fault_label`
- `lead_time_hours`
- `source_model`
- `model_version`
- `features_ref`
- `raw_output`
- `normalized_output`
- `metadata`
- `created_at`

### 3.3 필드 설명

- `observed_at`
  - 이 prediction이 대표로 참조하는 기준 시각

- `window_start`, `window_end`
  - 구간 예측이 필요한 경우만 사용하는 선택 필드

- `prediction_type`
  - `anomaly`, `fault`, `forecast`, `lead_time` 중 하나

- `severity`
  - Agent 판단에 사용할 위험도 축

- `raw_output`
  - ML 모델 원본 출력 JSON

- `normalized_output`
  - canonical schema로 변환하는 중간 정규화 결과 JSON

- `metadata`
  - 데이터셋별, 공급자별 추가 정보를 담는 확장 JSON

## 4. 최소 필드와 선택 필드

### 4.1 반드시 필요한 필드

- `prediction_id`
- `source_type`
- `schema_version`
- `substation_id`
- `observed_at`
- `prediction_label`
- `prediction_type`
- `prediction_score` 또는 `confidence`

### 4.2 있으면 좋은 필드

- `severity`
- `fault_label`
- `lead_time_hours`
- `model_version`
- `features_ref`

### 4.3 canonical prediction에 넣지 않을 필드

- 길게 늘어진 설명문
- 사용자 친화적 문장
- 화면용 문구
- 최종 권고문
- 작업 지시 문장

## 5. raw 입력과 adapter 계층

### 5.1 raw 입력이 직접 들어오는 이유

- 센서 데이터가 전처리되지 않은 상태로 들어올 수 있다.
- ML 출력이 아직 확정되지 않아도 Agent 흐름을 먼저 짜야 한다.
- raw와 normalized를 분리해야 디버깅이 쉬워진다.

### 5.2 adapter 역할

- ML 출력 형태를 표준화한다.
- 누락된 필드를 기본값으로 보정한다.
- Agent가 읽기 쉬운 구조로 변환한다.
- 새 데이터셋 필드는 canonical core를 바꾸지 않고 `metadata` 또는 adapter mapping으로 흡수한다.

### 5.3 adapter가 없을 때의 문제

- ML 출력이 조금만 바뀌어도 Agent 전체가 흔들린다.
- Tool과 LangGraph가 모델 내부 사정에 종속된다.
- DB 스키마가 불필요하게 자주 바뀐다.

## 6. Agent가 기대하는 입력 형태

Agent는 아래 두 가지를 구분해서 받는 것이 좋다.

- raw sensor event
- normalized prediction event

raw sensor event는 ingest / normalize 단계에서 처리하고,
normalized prediction event는 판단과 기록에 사용한다.

## 7. ML 팀에 요청할 최소 산출물

- 예측 결과 샘플 1개 이상
- label 정의
- score 또는 confidence 정의
- severity 사용 가능 여부
- raw output 예시

## 8. 정리

ML 모델의 최종 출력은 지금 완전히 몰라도 된다.
중요한 것은 Agent가 사용할 수 있는 최소 공통 구조를 먼저 고정하고,
데이터셋별 차이는 adapter와 확장 필드로만 처리하는 것이다.
