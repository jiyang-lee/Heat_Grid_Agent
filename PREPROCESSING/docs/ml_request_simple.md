# ML팀 요청 문서

## 1. 목적

PreDist 데이터셋으로 시계열 모델을 만들 때, Agent가 바로 쓸 수 있는 결과를 받고 싶습니다.

즉, 단순히 예측값만 주지 말고, `어느 기계실에서`, `언제`, `무슨 상태인지`, `얼마나 위험한지`가 같이 나오면 좋겠습니다.

## 2. 사용할 CSV

### 운영 시계열 CSV

#### manufacturer 1

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

### 라벨/이력 CSV

- `faults.csv`
- `disturbances.csv`
- `normal_events.csv`
- `feature_descriptions.csv`

## 3. ML팀이 해주면 좋은 일

아래처럼 결과를 만들어 주세요.

- 어떤 `substation ID`인지 알려주기
- 어떤 `timestamp` 구간을 예측했는지 알려주기
- 예측한 시계열 값 보여주기
- 이게 정상인지 이상인지 알려주기
- 위험도가 높은지 낮은지 점수로 알려주기
- 가능하면 고장 라벨도 같이 주기

## 4. 결과 형식 요청

최종 결과는 아래처럼 나오면 좋습니다.

```json
{
  "substation_id": 10,
  "timestamp": "2026-06-23 10:00:00",
  "prediction_label": "anomaly",
  "anomaly_score": 0.82,
  "confidence": 0.91,
  "severity": "high",
  "fault_label": "pump failure",
  "predicted_series": [],
  "estimated_lead_time": "6h"
}
```

## 5. 최소로 꼭 필요한 값

- `substation_id`
- `timestamp`
- `prediction_label`
- `anomaly_score` 또는 `confidence`
- `severity`
- `fault_label` 가능하면 추가
- `predicted_series`

## 6. 왜 이 값이 필요한가

Agent는 단순 예측값만 보고는 판단하기 어렵습니다.
그래서 ML 결과에 아래 정보가 같이 있어야 합니다.

- 어느 기계실인지
- 언제 발생한 예측인지
- 정상인지 이상인지
- 얼마나 위험한지
- 어떤 고장인지

이 정보가 있어야 Agent가 정규화하고 판단하고 우선순위를 정할 수 있습니다.

## 7. 한 줄 요약

ML팀은 `시계열 예측값 + 기계실 정보 + 이상 여부 + 위험도 + 가능하면 고장 라벨`까지 같이 주면 됩니다.
