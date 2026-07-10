# V2 운영 예측 1차 MVP 완료 판정표

실행 시각: 2026-07-08 17:16:38 +09:00

실행 기준:

- DB: `postgresql://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops`
- API: `POST /alerts/enqueue`
- 범위: CSV/windows fallback 기반 `priority_cards` 적재 후 urgent/high alert queue 확인

| 항목 | 결과 | 판정 |
| --- | ---: | --- |
| `priority_cards` 전체 개수 | 1252 | 완료 |
| urgent/high 카드 개수 | 147 | 완료 |
| `ops_alert_queue` open 개수 | 146 | 완료 |
| `ops_alert_queue` acked 개수 | 1 | 완료 |
| `ops_alert_queue.priority_score` 타입 | `double precision` | 완료 |
| 중복 enqueue `queued_count` | 0 | 완료 |
| 중복 enqueue `existing_count` | 147 | 완료 |

중복 enqueue 실행 결과:

```json
{
  "queued_count": 0,
  "existing_count": 147,
  "open_count": 146,
  "total_count": 147
}
```

판정: 1차 MVP는 완료 상태다. raw DB에서 `window_features`를 새로 만드는 생성기는 2차 범위로 남긴다.

## 고정 운영 시나리오

실행 시각: 2026-07-08 실제 script + API smoke 기준

| 단계 | 호출 | 결과 |
| --- | --- | --- |
| 1 | `scripts/simulate_predictor_db.py --append --enqueue-alerts` | `fallback_source=csv_windows`, `queued_count=0`, `existing_count=147` |
| 2 | `POST /alerts/enqueue` | `queued_count=0`, `existing_count=147`, `open_count=146`, `total_count=147` |
| 3 | `GET /alerts?status=open&priority_level=urgent` | urgent alert 선택 |
| 4 | `POST /alerts/{alert_id}/simulate` | `200 OK`, `agent_mode=fallback`, resolved `card_id` 반환 |
| 5 | `POST /alerts/{alert_id}/ack` | `status=acked`, `acked_by=fixed-scenario` |

고정 선택값:

| 항목 | 값 |
| --- | --- |
| `alert_id` | `06b4159a-77bc-e8f1-b562-4bf2b61fefb5` |
| `card_id` | `aa2a3d86-46fe-5159-9731-c7fed5dc7c54` |
| `priority_level` | `urgent` |
| simulate summary | `manufacturer 1 substation 8에서 urgent priority 카드가 생성됐습니다.` |

이 흐름은 `tests/test_v2_postgres_react_ops.py::test_v2_postgres_fixed_ops_scenario_runs_from_enqueue_to_ack`로 고정했다.

## 6번 입력 계약

운영보조 에이전트의 기본 시작점은 전체 DB가 아니라 urgent/high `ops_alert_queue`다.

| 입력 | 용도 | 상태 |
| --- | --- | --- |
| `alert_id` | alert queue에서 선택한 urgent/high 알림을 바로 설명한다. 기본 입력이다. | `POST /alerts/{alert_id}/simulate` |
| `card_id` | 이미 카드가 특정된 경우 직접 설명한다. 보조 입력이다. | `POST /simulate/{card_id}` |

6번 흐름은 `GET /alerts?status=open`에서 alert를 고른 뒤 `alert_id`로 설명을 요청하는 계약으로 확정한다.
