# Agent 팀 전달 문서 - Tool I/O handoff

## 1. 목적

이 문서는 LangChain / LangGraph 담당 팀원이 바로 설계를 시작할 수 있게 하기 위한 handoff 문서다.

이번에 이미 고정된 것은 아래와 같다.

- canonical prediction schema
- DB 5축
- Agent 작업 위치: `agent/`
- 기준 브랜치: `agent`
- Tool 3개 이름
- Tool 3개 입출력 shape

## 2. 지금 바로 참고할 파일

- `agent/schemas/canonical_prediction.py`
- `agent/repository/db_schema.py`
- `docs/plan/04_tool_io_contract.md`
- `agent/notebooks/00_agent_db_schema.ipynb`

## 3. Tool 3개 요약

### ingest_normalize_tool

- 입력: PreDist raw row 기반 payload
- 출력:
  - `raw_event`
  - `normalized_feature`
- DB 매핑:
  - `raw_sensor_events`
  - `normalized_sensor_features`

### predict_adapter_tool

- 입력: ML output mock + feature reference
- 출력:
  - `prediction`
- DB 매핑:
  - `model_predictions`

### decision_tool

- 입력: canonical prediction + history context
- 출력:
  - `decision`
- DB 매핑:
  - `agent_decisions`

## 4. 팀원이 설계할 범위

- `decision_tool` 내부 rule
- priority score 계산
- State 실제 사용 방식
- node 분기 조건
- fallback 세부 정책
- LangChain orchestration
- LangGraph state / node / edge

## 5. Agent A가 이미 고정한 경계

- tool 이름
- tool 입력 shape
- tool 출력 shape
- DB row-ready payload 기준
- canonical prediction 매핑 규칙
- 최소 State 필드 후보

## 6. 최소 State 필드

```json
{
  "raw_event": {},
  "normalized_feature": {},
  "prediction": {},
  "decision": {},
  "history_context": {},
  "fallback_flag": false,
  "log_refs": []
}
```

## 7. mock 흐름

1. PreDist row
2. `ingest_normalize_tool`
3. ML mock output
4. `predict_adapter_tool`
5. canonical prediction
6. `decision_tool`
7. decision output

## 8. 주의할 점

- Agent A는 rule 자체를 아직 고정하지 않았다.
- 따라서 `decision_tool` 내부 판단 기준은 팀원 설계 범위다.
- 하지만 출력 shape와 DB 매핑은 이미 고정되어 있으므로, 그 shape를 깨지 않는 방향으로 설계해야 한다.

## 9. 한 줄 정리

팀원은 지금부터 **rule / state / node / orchestration** 설계를 시작하면 되고,  
tool I/O shape와 DB 연결 기준은 Agent A가 먼저 고정해 둔 상태다.
