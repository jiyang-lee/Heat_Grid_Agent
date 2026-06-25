# data/

원천 센서 CSV는 대용량이라 **git에 커밋하지 않는다**(`.gitignore`에서 `/data/*` 제외, 이 README만 추적).
새 환경에서는 아래 구조로 데이터를 채운 뒤 작업한다.

## 기대 구조

```
data/
  manufacturer 1/
    operational_data/substation_1~35.csv      # 35개
    faults.csv  disturbances.csv  normal_events.csv  feature_descriptions.csv
  manufacturer 2/
    operational_data/substation_*.csv          # 58개 (결번 22, 30, 32)
    faults.csv  disturbances.csv  normal_events.csv  feature_descriptions.csv
```

- `operational_data/*.csv`: 실시간 센서 시계열, 수집 주기 10분, 구분자 `;`. **raw 적재 대상.**
- `faults / disturbances / normal_events`: 라벨/이벤트 → 후속 단계 join (raw에는 넣지 않음).
- `feature_descriptions.csv`: 센서 설명·단위 사전.

자세한 컬럼/단위/주의점은 [../docs/plan/07_raw_sensor_data_schema.md](../docs/plan/07_raw_sensor_data_schema.md) 참고.
