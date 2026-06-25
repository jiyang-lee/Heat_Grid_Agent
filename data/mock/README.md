# 목 데이터 계약 — `mock_ml_output.csv` (ML output 레벨)

데모 한 사이클은 실 raw/실 ML output/실DB 없이 이 한 파일로 구동한다.
1행 = 1 윈도우(기계실 × 6시간). ≈300행(normal/pre_fault 혼합, 여러 substation·여러 manufacturer).
실 ML output 도착 시 경로만 교체하면 priority+agent 파이프라인은 그대로 동작한다.

> 컬럼명은 mlmodel1 `agent_full_data_contract.json` 의 `priority_engine.input_columns` + `ml_outputs`
> + 라벨/컨텍스트 컬럼과 정합한다. 단, 실 ML output의 `main_abnormal_features` 는 본 데모 계약에서
> `main_abnormal_sensors` 로 부르며 `run_priority` 어댑터가 매핑한다.

## 컬럼 (순서 고정)

| # | 컬럼 | 타입 | 의미 |
|---|---|---|---|
| 1 | `manufacturer` | str | 제조사 식별자 (예: `manufacturer_1`) |
| 2 | `substation_id` | int | 기계실 식별자 |
| 3 | `window_start` | ISO datetime | 윈도우 시작 |
| 4 | `window_end` | ISO datetime | 윈도우 종료(=start+6h) |
| 5 | `anomaly_score` | float[0,1] | 이상 정도 (priority 피처) |
| 6 | `risk_score` | float[0,100] | 위험 점수 |
| 7 | `risk_probability` | float[0,1] | 위험 확률 (priority 피처) |
| 8 | `risk_level_calibrated` | enum | `low/medium/high/critical` |
| 9 | `predicted_lead_time_bucket` | enum | `0-24h/1-3d/3-7d` |
| 10 | `predicted_lead_time_confidence` | float[0,1] | 리드타임 신뢰도 (priority 피처) |
| 11 | `leadtime_prob_0-24h` | float[0,1] | 0-24h 확률 (priority 피처) |
| 12 | `leadtime_prob_1-3d` | float[0,1] | 1-3d 확률 (priority 피처) |
| 13 | `leadtime_prob_3-7d` | float[0,1] | 3-7d 확률 (priority 피처) |
| 14 | `lead_time_bucket_distance` | int | argmax bucket 거리 |
| 15 | `days_since_last_fault_event` | float | 최근 고장 이후 일수 |
| 16 | `days_since_last_task_event` | float | 최근 정비 이후 일수 |
| 17 | `days_since_last_any_event` | float | 최근 임의 이벤트 이후 일수 |
| 18 | `configuration_type` | str | 설비 구성(예: `sh_dhw`) |
| 19 | `has_dhw` | int{0,1} | DHW 보유 |
| 20 | `has_buffer_tank` | int{0,1} | 버퍼탱크 보유 |
| 21 | `main_abnormal_sensors` | str | 주요 이상 센서(세미콜론 구분) |
| 22 | `label` | enum | `normal/pre_fault` |
| 23 | `fault_label` | str | 고장 유형(없으면 공란) |
| 24 | `estimated_lead_time_hours` | float | 추정 리드타임(시간, normal은 공란) |
| 25 | `lead_time_bucket` | enum | `0-24h/1-3d/3-7d` (normal은 공란) |

## priority 모델 입력 7피처
`anomaly_score, risk_probability, risk_score, leadtime_prob_0-24h, leadtime_prob_1-3d, leadtime_prob_3-7d, predicted_lead_time_confidence`

## priority 라벨 유도 (학습셋 전용)
`label`+`lead_time_bucket` → `normal=0 / 3-7d=33 / 1-3d=66 / 0-24h=100`.
leakage guard: 학습 윈도우는 `window_end ≤ report_date`.

## 생성
이 데모에서는 Codex 대신 `agent/priority/generate_mock.py` 가 본 계약대로 ≈300행을 생성한다
(`uv run python -m agent.priority.generate_mock`). 신호 구조: pre_fault 윈도우일수록 anomaly/risk/임박
리드타임 확률이 높고 정상 윈도우는 낮게 — priority 모델이 학습할 수 있는 단조 관계를 갖도록 구성.
