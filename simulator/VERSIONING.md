# 시뮬레이션 버전

## Current

```text
v2_postgres_react_ops
```

PostgreSQL priority card를 읽고 LangGraph/LangChain ReAct Agent가 `get_ops_evidence(card_id)` 툴을 호출해 운영 답변을 생성한다.

## Notes

- `agent/simulation` 브랜치는 머지하지 않고 보존한다.
- 이 버전은 `develop2 + origin/agent/mlmodel` 기준으로 정리한 PostgreSQL 운영 보조 서버다.
- 외부 context/weather/RAG 툴은 아직 노출하지 않는다.

## v1 vs v2 비교

v1(`v1_langgraph_react_ops`, 미병합 `origin/agent/simulation` 브랜치 전용)과 v2(현재 버전)의 목적/데이터 원천/API 범위 상세 비교는 [docs/16_SIMULATION_VERSIONS.md](../docs/16_SIMULATION_VERSIONS.md) 참고.
