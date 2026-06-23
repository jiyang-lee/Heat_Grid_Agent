# HeatGrid Agent ML 산출물 계약

이 문서는 ML 파트가 **직접 우선순위를 계산하지 않고**, Agent가 통합 판단할 수 있도록 어떤 산출물을 어떤 형태로 넘겨야 하는지 정의한다.

## 1. 역할 구분

### ML이 하는 일

- 시계열에서 이상 징후를 탐지한다.
- 고장신고 전후 패턴과의 유사도를 계산한다.
- 앞으로 얼마만큼의 시간 안에 문제가 발생할 가능성이 있는지 리드타임 후보를 만든다.
- 센서별 이상 기여도를 계산한다.
- 구간별, 기계실별 예측 근거를 제공한다.

### ML이 하지 않는 일

- 우선 점검 대상의 최종 결정
- 작업 우선순위 산정
- 운영자에게 바로 전달할 최종 판단 생성

최종 통합 판단은 Agent가 수행한다.

## 2. ML이 제공해야 할 핵심 산출물

ML이 넘겨야 할 산출물은 단순한 점수 하나가 아니라, 다음 다섯 축으로 구성하는 것이 좋다.

1. 이상 탐지 결과
2. 위험 가능성 결과
3. 리드타임 결과
4. 센서/구간별 근거
5. 메타데이터

## 3. 산출물 상세

### 3.1 이상 탐지 결과

목적:

- 현재 구간이 정상 패턴에서 얼마나 벗어났는지 보여준다.

권장 필드:

- `substation_id`
- `window_start`
- `window_end`
- `anomaly_score`
- `anomaly_label`
- `anomaly_threshold`
- `model_version`

설명:

- `anomaly_score`는 이상 정도를 나타내는 연속값이다.
- `anomaly_label`은 임계값 기준의 이진 판정이다.
- Agent는 이 값을 근거 중 하나로만 사용한다.

### 3.2 위험 가능성 결과

목적:

- fault/maintenance 이력과 유사한 패턴인지 보여준다.

권장 필드:

- `substation_id`
- `window_start`
- `window_end`
- `risk_score`
- `risk_class`
- `reference_event_id`
- `reference_event_type`
- `model_version`

설명:

- `risk_score`는 고장신고 또는 정비 이벤트와의 유사성/위험 가능성을 나타낸다.
- `reference_event_id`는 비교 기준이 된 사건 식별자다.
- Agent는 이 값을 리드타임과 함께 해석한다.

### 3.3 리드타임 결과

목적:

- 지금부터 얼마 이내에 문제가 현실화될 가능성이 있는지 추정한다.

권장 필드:

- `substation_id`
- `window_start`
- `window_end`
- `lead_time_hours`
- `lead_time_bucket`
- `lead_time_confidence`
- `model_version`

설명:

- `lead_time_hours`는 기대되는 발생까지 남은 시간 추정값이다.
- `lead_time_bucket`은 예: `0-6h`, `6-24h`, `1-3d`, `3d+` 같은 구간형 값이다.
- Agent는 이 값을 우선 점검 시점 판단에 사용한다.

### 3.4 센서/구간별 근거

목적:

- 어떤 센서와 어떤 구간이 결과에 영향을 주었는지 설명한다.

권장 필드:

- `substation_id`
- `window_start`
- `window_end`
- `top_sensors`
- `sensor_scores`
- `top_time_segments`
- `pattern_notes`

설명:

- `top_sensors`는 영향도가 큰 센서 목록이다.
- `sensor_scores`는 센서별 기여 점수 또는 중요도다.
- `top_time_segments`는 이상이 강하게 나타난 세부 시간 구간이다.
- `pattern_notes`는 사람이 읽을 수 있는 짧은 설명이다.

### 3.5 메타데이터

목적:

- 결과 재현성과 버전 관리를 가능하게 한다.

권장 필드:

- `substation_id`
- `window_start`
- `window_end`
- `feature_version`
- `model_version`
- `data_version`
- `created_at`
- `training_period`
- `source_dataset`

## 4. Agent에게 어떻게 넘길 것인가

ML 결과는 Agent가 읽기 쉬운 단위로 저장해야 한다.

권장 방식:

- 기계실별 결과를 행 단위로 저장
- 시간 구간별 결과를 별도 테이블 또는 파일로 저장
- 각 결과에 `substation_id`와 시간 구간을 반드시 포함
- 요약본과 상세본을 분리

### 4.1 추천 저장 포맷

#### 요약 테이블

1행 = 1기계실 + 1시간 윈도우 또는 1예측 구간

예:

```text
substation_id | window_start | window_end | anomaly_score | risk_score | lead_time_hours | top_sensors
```

#### 상세 테이블

1행 = 1기계실 + 1예측 구간 + 세부 설명

예:

```text
substation_id | window_start | window_end | sensor_scores | top_time_segments | pattern_notes | metadata_json
```

#### JSON export

Agent 연동이 쉬우도록 최종적으로는 JSON도 함께 제공하는 것이 좋다.

예:

```json
{
  "substation_id": 12,
  "window_start": "2026-06-23T00:00:00",
  "window_end": "2026-06-23T01:00:00",
  "anomaly": {
    "score": 0.87,
    "label": 1,
    "threshold": 0.62
  },
  "risk": {
    "score": 0.73,
    "class": "high",
    "reference_event_id": "fault_104"
  },
  "lead_time": {
    "hours": 18,
    "bucket": "6-24h",
    "confidence": 0.71
  },
  "evidence": {
    "top_sensors": ["p_hc1_supply_temperature", "s_dhw_return_temperature"],
    "sensor_scores": {
      "p_hc1_supply_temperature": 0.91,
      "s_dhw_return_temperature": 0.78
    }
  },
  "metadata": {
    "model_version": "ml_v1",
    "feature_version": "feature_v1",
    "data_version": "predist_v2"
  }
}
```

## 5. 결과 해석 규칙

Agent가 혼동하지 않도록 ML 결과 의미를 분리해야 한다.

- `anomaly_score` = 현재 패턴이 얼마나 이상한가
- `risk_score` = 과거 fault/maintenance와 얼마나 유사한가
- `lead_time_hours` = 문제가 발생할 가능성이 있는 시간적 여유
- `top_sensors` = 어떤 센서가 근거가 되었는가

이 네 가지를 합쳐서 Agent가 우선 점검 대상을 결정한다.

즉, **ML은 점수 묶음을 제공하고, Agent가 우선순위를 만든다.**

## 6. 최소 구현 순서

1. substation 단위 윈도우 데이터 생성
2. anomaly score 산출
3. risk score 산출
4. lead time bucket 산출
5. top sensor 추출
6. JSON export 생성
7. CSV 또는 Parquet 저장
8. Agent가 읽는 스키마 문서화

## 7. 실무 규칙

- 한 번에 하나의 기계실과 하나의 시간 구간을 읽을 수 있어야 한다.
- 점수는 항상 원본 근거와 함께 저장한다.
- 우선순위 판단은 여기서 하지 않는다.
- 결과 계약은 바뀌면 안 되므로 버전 필드를 반드시 둔다.
- 나중에 Agent가 결과를 조합할 수 있도록 형태를 단순하게 유지한다.
