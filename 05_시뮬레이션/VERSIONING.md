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
