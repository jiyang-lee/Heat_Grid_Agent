# ML 팀 요청 문서: Agent 전달용 산출물 규격

이 문서는 PreDist 데이터로 시계열 모델을 학습한 뒤, **Agent가 바로 쓸 수 있는 형태로 ML 결과를 넘기기 위한 규격**이다.

핵심은 다음과 같다.

- ML은 최종 우선순위를 정하지 않는다.
- ML은 Agent가 판단할 수 있도록 예측 근거와 상태 정보를 함께 제공한다.
- Agent는 ML 결과, 설비 구성, 이력 정보를 통합해서 최종 판단을 수행한다.

## 1. ML이 제공해야 하는 정보

최소한 아래 정보가 함께 나와야 한다.

- 어느 기계실인지
- 어느 시점 또는 어느 구간인지
- 정상인지 이상인지
- 얼마나 위험한지
- 어떤 고장 유형과 유사한지
- 어떤 센서가 근거였는지
- 앞으로 얼마나 빨리 문제가 현실화될 수 있는지

## 2. 사용 데이터

### 2.1 운영 시계열 CSV

#### manufacturer 1

주요 컬럼:

- `timestamp`
- `outdoor_temperature`
- `s_hc1_supply_temperature`
- `s_hc1_supply_temperature_setpoint`
- `s_dhw_supply_temperature`
- `s_dhw_supply_temperature_setpoint`
- `p_hc1_return_temperature`
- `s_dhw_upper_storage_temperature`
- `s_dhw_lower_storage_temperature`
- `p_net_meter_energy`
- `p_net_meter_volume`
- `p_net_meter_heat_power`
- `p_net_meter_flow`
- `p_net_supply_temperature`
- `p_net_return_temperature`

#### manufacturer 2

주요 컬럼:

- `timestamp`
- `s_dhw_supply_temperature_setpoint`
- `outdoor_temperature`
- `s_hc1_control_unit_mode`
- `s_dhw_control_unit_mode`
- `s_hc1_room_temperature_setpoint`
- `p_hc1_return_temperature_setpoint`
- `p_hc1_return_temperature`
- `p_dhw_return_temperature`
- `s_dhw_upper_storage_temperature`
- `s_dhw_lower_storage_temperature`
- `p_hc1_control_valve_position_setpoint`
- `p_dhw_control_valve_position`
- `s_hc1_heating_pump_status_setpoint`
- `s_hc1_supply_temperature_setpoint`
- `s_hc1_supply_temperature`
- `s_dhw_supply_temperature`
- `p_net_meter_energy`
- `p_net_meter_flow`
- `p_net_meter_heat_power`
- `p_net_return_temperature`
- `p_net_meter_volume`
- `p_net_supply_temperature`

### 2.2 라벨/이력 CSV

- `faults.csv`
- `disturbances.csv`
- `normal_events.csv`
- `feature_descriptions.csv`

## 3. ML 산출물의 역할

ML 결과는 우선순위가 아니라 **판단 재료**여야 한다.

즉, ML이 해줘야 하는 것은 다음이다.

- 예측값 제공
- 이상 여부 제공
- 위험도 제공
- 리드타임 제공
- 고장 라벨 후보 제공
- 근거 센서 제공

Agent가 이 정보를 조합해서 최종 결과를 만든다.

## 4. 필수 산출물

ML 결과에는 최소 아래 필드가 들어가야 한다.

- `substation_id`
- `timestamp`
- `prediction_label`
- `anomaly_score` 또는 `confidence`
- `severity`
- `fault_label` 가능하면 추가
- `predicted_series`

## 5. 권장 산출물

Agent가 더 잘 판단할 수 있도록 아래 필드를 함께 제공하는 것을 권장한다.

- `lead_time_hours`
- `lead_time_bucket`
- `lead_time_confidence`
- `risk_score`
- `risk_class`
- `top_sensors`
- `sensor_scores`
- `window_start`
- `window_end`
- `model_version`
- `feature_version`
- `data_version`
- `created_at`

## 6. 필드 의미

### 6.1 `substation_id`

어느 기계실의 결과인지 식별한다.

### 6.2 `timestamp`

예측 시점 또는 결과가 대표하는 기준 시각이다.

### 6.3 `prediction_label`

예측 상태를 문자열로 표시한다.

권장 값 예시:

- `normal`
- `anomaly`
- `warning`
- `high_risk`

### 6.4 `anomaly_score`

현재 시계열이 정상 패턴에서 얼마나 벗어났는지 나타내는 점수다.

### 6.5 `confidence`

예측의 신뢰도를 나타낸다. 모델 특성상 `anomaly_score` 대신 혹은 함께 둘 수 있다.

### 6.6 `severity`

Agent가 읽을 수 있도록 위험 수준을 범주형으로 제공한다.

권장 값 예시:

- `low`
- `medium`
- `high`
- `critical`

### 6.7 `fault_label`

가능하면 고장 유형 후보를 함께 제공한다.

예:

- `pump failure`
- `sensor fault`
- `valve abnormality`
- `temperature control issue`

### 6.8 `predicted_series`

예측한 시계열 값 또는 미래 구간 예측값이다.

형태 예시:

```json
[
  {"timestamp": "2026-06-23 10:00:00", "value": 42.1},
  {"timestamp": "2026-06-23 11:00:00", "value": 41.7}
]
```

## 7. 권장 JSON 응답 형식

최종 결과는 아래처럼 주는 것이 가장 다루기 쉽다.

```json
{
  "substation_id": 10,
  "timestamp": "2026-06-23 10:00:00",
  "window_start": "2026-06-23 09:00:00",
  "window_end": "2026-06-23 10:00:00",
  "prediction_label": "anomaly",
  "anomaly_score": 0.82,
  "confidence": 0.91,
  "severity": "high",
  "fault_label": "pump failure",
  "lead_time_hours": 6,
  "lead_time_bucket": "0-6h",
  "lead_time_confidence": 0.74,
  "risk_score": 0.67,
  "risk_class": "high",
  "top_sensors": [
    "p_hc1_return_temperature",
    "s_hc1_supply_temperature"
  ],
  "predicted_series": [
    {"timestamp": "2026-06-23 11:00:00", "value": 41.8},
    {"timestamp": "2026-06-23 12:00:00", "value": 42.0}
  ],
  "model_version": "iforest_v1",
  "feature_version": "feature_v1",
  "data_version": "predist_v2",
  "created_at": "2026-06-23T10:05:00"
}
```

## 8. Agent가 이 결과를 어떻게 쓰는가

Agent는 다음 순서로 해석한다.

1. `substation_id`로 대상 기계실을 식별한다.
2. `timestamp`와 `window_start` / `window_end`로 시간 축을 맞춘다.
3. `prediction_label`, `anomaly_score`, `severity`로 상태를 확인한다.
4. `fault_label`과 `risk_score`로 고장 가능성 후보를 본다.
5. `lead_time_hours`로 점검 시점을 가늠한다.
6. `top_sensors`와 `predicted_series`로 판단 근거를 확인한다.
7. 설비 구성과 이력 정보를 합쳐 최종 판단을 만든다.

## 9. ML팀 구현 기준

ML팀은 아래를 구현하면 된다.

- 시계열 전처리
- 윈도우 생성
- 이상탐지 모델
- 위험도 모델
- 리드타임 추정
- 고장 라벨 후보 출력
- 예측 시계열 출력
- JSON/CSV export

ML팀은 아래를 하지 않는다.

- 최종 우선순위 결정
- 운영자 전달 여부 결정
- 작업지시서 작성

## 10. 한 줄 정리

ML팀은 `시계열 예측값 + 기계실 정보 + 이상 여부 + 위험도 + 리드타임 + 가능하면 고장 라벨`을 함께 주면 된다.  
Agent는 그 결과를 설비 구성과 이력 정보까지 합쳐서 최종 판단한다.
