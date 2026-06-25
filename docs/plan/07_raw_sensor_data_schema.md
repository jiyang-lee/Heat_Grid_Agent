# raw_sensor_data 스키마 초안

## 1. 목적

5단계 파이프라인 1단계(원천 데이터)의 적재 대상과 칼럼을 확정한다.
핵심은 "분석용 가공"이 아니라 **실시간 센서값 원본 보존**이다.

- 적재 대상: 제조사 2곳의 `operational_data`(실시간 센서 시계열).
- **고장/이상 라벨은 raw에 넣지 않는다.** 실시간으로 들어오는 센서 한 행에는 고장 라벨이 없고,
  고장 판정은 후속 predict 단계의 출력이기 때문이다(라벨을 raw에 넣으면 데이터 누수).

## 2. 활용 파일

### 2.1 원천 (raw 적재 대상)

| 경로 | 개수 | 비고 |
|---|---|---|
| `data/manufacturer 1/operational_data/substation_1~35.csv` | 35 | 1~35 전부 |
| `data/manufacturer 2/operational_data/substation_1~61.csv` | 58 | 결번 22, 30, 32 |

- 총 93개 파일, 수집 주기 10분, CSV 구분자 `;`.
- **파일 내부에 설비 ID 칼럼이 없다.** `manufacturer`(폴더명), `substation_id`(파일명 `substation_{N}`)가 유일한 출처다.

### 2.2 라벨/보조 파일 (raw 제외 — 후속 단계 join)

| 파일 | 용도 |
|---|---|
| `faults.csv` | 고장 이벤트·라벨 → 후속 라벨링 단계 |
| `disturbances.csv` | 외란 이벤트 → 후속 단계 |
| `normal_events.csv` | 정상 이벤트 → 후속 단계 |
| `feature_descriptions.csv` | 센서 설명·단위 사전 → 단위 해석 |

## 3. 칼럼 구성

raw 한 행 = **식별 3개 + 센서값 9개(+선택 1개) + 추적/운영 4개**.

### 3.1 CSV에서 그대로 들어오는 칼럼 (만들 필요 없음)

- `timestamp` — 측정 시각(10분 간격)
- 센서값 9개(4장) + `outdoor_temperature`(선택)

### 3.2 내가 만들어 넣어야 하는 칼럼 (CSV에 없음)

| 구분 | 칼럼 | 출처/생성 | 이유 |
|---|---|---|---|
| 필수 | `manufacturer` | 폴더명 → `m1`/`m2` | 설비 식별 + **단위 해석 키** |
| 필수 | `substation_id` | 파일명 `substation_{N}` | 설비 식별 (CSV 내부에 없음) |
| 권장 | `source_file` | 적재 시 | 원본 파일 역추적 |
| 권장 | `source_row` | 적재 시 | 원본 행 추적·중복 적재 점검 |
| 권장 | `ingested_at` | 적재 시 | 적재 시각(측정 시각과 분리) |
| 권장 | `ingest_batch_id` | 적재 시 | 재적재/멱등성 관리 |

> 필수 2개(`manufacturer`, `substation_id`)만으로도 raw는 동작한다. 권장 4개는 추적성·운영용.

## 4. 센서값 칼럼 (전 93개 파일 공통)

두 제조사 모든 operational 파일에 빠짐없이 존재하는 칼럼이다(원본 CSV 헤더에서 직접 확인).
정렬은 `_` 첫 토큰(`p`/`s`) → 둘째 토큰(`hc1`/`net`) 순.

| 칼럼 | 의미 | 단위 (M1 / M2) | 타입 |
|---|---|---|---|
| `p_hc1_return_temperature` | 난방회로1 1차 환수온도 | °C / °C | measure |
| `p_net_supply_temperature` | 1차 공급온도 | °C / °C | measure |
| `p_net_return_temperature` | 1차 환수온도 | °C / °C | measure |
| `p_net_meter_heat_power` | 순시 열출력 | kW / W | measure |
| `p_net_meter_flow` | 순시 유량 | l/h / ml/h | measure |
| `p_net_meter_energy` | 적산 열량 | kWh / Wh | meter(누적) |
| `p_net_meter_volume` | 적산 체적 | m³ / ml | meter(누적) |
| `s_hc1_supply_temperature` | 2차 난방 공급온도 | °C / °C | measure |
| `s_hc1_supply_temperature_setpoint` | 2차 난방 공급 설정온도 | °C / °C | setpoint |

선택: `outdoor_temperature`(외기온도, °C) — M1 35개 전부에 있으나 M2엔 일부만 존재 → **nullable**로 추가 권장.

## 5. 주의점

- **단위가 제조사별로 다르다**: meter 4종(`heat_power`/`flow`/`energy`/`volume`)이 M1·M2 단위 상이(예: energy `kWh` vs `Wh`).
  `manufacturer`를 함께 적재해야 후속 단위 정규화가 가능하다. raw는 원시값 그대로 보존하고, 환산은 후속 단계로 미룬다.
- `outdoor_temperature.1`(M2 substation 21·57): pandas가 외기온도 중복명에 붙인 칼럼 → raw에선 무시한다.
- `*_setpoint`·`*_mode`·`*_status`(설정/모드/상태)와 하위 난방회로(`s_hc1.1~3`)·급탕(`s_dhw_*`) 칼럼은 설비별 편차가 커
  전 파일 공통이 아니므로 실시간 코어에서 제외한다(필요 시 후속 확장).

## 6. 테이블 스키마 (DDL 스케치, wide)

```sql
CREATE TABLE raw_sensor_data (
  -- 식별 (CSV에 없음 → 적재 시 생성)
  manufacturer   TEXT       NOT NULL,            -- 'm1' | 'm2' (폴더명)
  substation_id  INTEGER    NOT NULL,            -- substation_{N} (파일명)
  timestamp      TIMESTAMP  NOT NULL,            -- CSV 측정 시각 (10분 간격)

  -- 센서값 (CSV 그대로, 전 93파일 공통)
  p_hc1_return_temperature           DOUBLE PRECISION,
  p_net_supply_temperature           DOUBLE PRECISION,
  p_net_return_temperature           DOUBLE PRECISION,
  p_net_meter_heat_power             DOUBLE PRECISION,
  p_net_meter_flow                   DOUBLE PRECISION,
  p_net_meter_energy                 DOUBLE PRECISION,
  p_net_meter_volume                 DOUBLE PRECISION,
  s_hc1_supply_temperature           DOUBLE PRECISION,
  s_hc1_supply_temperature_setpoint  DOUBLE PRECISION,
  outdoor_temperature                DOUBLE PRECISION,   -- M2 일부 결번 → nullable

  -- 추적·운영 (적재 시 생성, 선택)
  source_file      TEXT,
  source_row       INTEGER,
  ingested_at      TIMESTAMP,
  ingest_batch_id  TEXT,

  PRIMARY KEY (manufacturer, substation_id, timestamp)
);
```

> `timestamp`는 PostgreSQL 타입 키워드와 겹쳐 쿼리 시 따옴표가 필요할 수 있다. 충돌이 불편하면 `event_time`으로 바꾼다.

### 6.1 CSV 한 행 → raw 한 행 (wide 직결)

원본 (manufacturer 1 substation_1, 일부 칼럼):

```
timestamp           ; outdoor_temperature ; p_net_supply_temperature ; p_net_meter_energy
2018-06-10 00:40:00 ; 14.3                ; 71.2                     ; 1234
```

raw_sensor_data (식별자 추가 + 센서값 그대로):

```
manufacturer | substation_id | timestamp           | outdoor_temperature | p_net_supply_temperature | p_net_meter_energy | ...
m1           | 1             | 2018-06-10 00:40:00 | 14.3                | 71.2                     | 1234               | ...
```

## 7. 정리

- raw = `operational_data`의 실시간 센서값 원본 보존. 고장 라벨은 제외(후속 join).
- 칼럼 = CSV에서 오는 것(`timestamp` + 센서 9개 + 선택 외기) + 내가 만드는 것(식별 2 필수, 추적 4 권장).
- wide 포맷: 전 93파일 공통 센서를 칼럼으로 고정한다. setpoint/mode/status·하위회로·급탕 등 설비별 편차 칼럼은 후속 확장으로 미룬다.