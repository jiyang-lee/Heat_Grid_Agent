# v2_postgres_react_ops

`develop2` 기준 PostgreSQL 입력을 읽는 최소 ReAct 운영 보조 에이전트다.

## Run

```powershell
uv run python simulator/versions/v2_postgres_react_ops/backend/server.py
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

## 데이터 적재 명령

- 기본 적재(기존 DB 치환):  
  `uv run python scripts/simulate_predictor_db.py`
- 모델 출력 포함 적재:  
  `uv run python scripts/simulate_predictor_db.py --model-run-id <UUID>`
- 기존 데이터 유지하고 추가 적재:  
  `uv run python scripts/simulate_predictor_db.py --append`
- 기본 실행은 `TRUNCATE ... CASCADE`로 기존 시뮬레이션 입력 테이블을 일괄 교체한다.
