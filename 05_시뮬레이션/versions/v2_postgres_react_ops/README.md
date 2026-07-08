# v2_postgres_react_ops

`develop2` 기준 PostgreSQL 입력을 읽는 최소 ReAct 운영 보조 에이전트다.

## Run

```powershell
uv run python 05_시뮬레이션/versions/v2_postgres_react_ops/backend/server.py
```

기본 주소:

```text
http://127.0.0.1:8002
```

## Flow

```mermaid
flowchart TD
  A["priority card_id"] --> B["LangGraph ReAct Agent"]
  B --> C["tool: get_ops_evidence(card_id)"]
  C --> B
  B --> D["summary/action_plan/caution"]
  D --> E["Pydantic 검증"]
  E --> F["SSE/API 응답"]
```

## Structure

```text
backend/
  server.py
  repository.py
  queries.py
  schemas.py
  settings.py
  usage.py
frontend/
  index.html
  static/app.js
  static/styles.css
contracts/
  ops_agent_output.schema.json
db/
  seed_or_import.md
```

## Runtime

- 입력 원천: PostgreSQL
- 기본 DB: `postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops`
- DB 변경: `HEATGRID_DATABASE_URL`
- OpenAI 키: `OPENAI_API_KEY`
- 활성 Agent tool: `get_ops_evidence(card_id)` 하나
- 외부 context/weather/RAG tool은 아직 노출하지 않는다.
