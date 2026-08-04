# Replay 운영 Runbook

## 시작 전 확인

- `HEATGRID_REPLAY_ENABLED=true`와 Import가 필요한 경우 `HEATGRID_REPLAY_IMPORT_ENABLED=true`를 설정한다.
- `heatgrid-db-migrate verify`가 성공하고, `demo_replay.zip` SHA-256이 등록값과 일치해야 한다.
- 저장소에 최소 5 GiB 여유 공간이 있어야 한다.

## Worker

별도 프로세스로 `uv run heatgrid-replay-worker`를 실행한다. API 프로세스는 명령·Snapshot·SSE만 제공하며 Tick을 직접 실행하지 않는다. `replay_runs.lease_owner`, `lease_expires_at`, `heartbeat_at`으로 소유권과 장애 복구 상태를 확인한다.

## 장애 복구

1. Run을 pause 또는 cancel한다.
2. lease 만료 뒤 다른 Worker가 claim했는지 확인한다.
3. `replay_tick_batches`의 마지막 sequence와 `replay_runs.last_emitted_sequence`을 비교한다.
4. 36 Tick 경계는 `replay_window_evaluations(run_id, window_end)` 유니크 키를 확인한다.
5. Browser는 `Last-Event-ID`로 `replay_stream_events`를 재연결하고, 보존 범위를 넘기면 Snapshot을 다시 요청한다.

## 롤백과 안전 경계

- Replay 원시 Tick은 `replay_*` 테이블에 원본 배치로 보존하고, 시연 UI가 기존 운영 센서 흐름을 그대로 사용할 수 있도록 `sensor_readings`에도 센서별 row로 투영한다. Replay 투영값은 `source_file='synthetic-replay:<run_id>'`로 표식한다.
- 기본 운영 평가/Alert는 `stream_key='default'`, Replay는 `replay:<run_id>`로 분리된다.
- Replay Alert는 `synthetic=true`이며 자동 재학습·자동 승인 대상이 아니다.
- migration은 roll-forward만 허용하며, 적용된 SQL 파일을 수정하지 않는다.
