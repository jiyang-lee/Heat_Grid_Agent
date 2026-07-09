# v2_postgres_react_ops

`develop2` 기준 PostgreSQL 입력을 읽는 HeatGrid 운영 보조 API 서버다.
이 서버는 프론트 정적 파일을 서빙하지 않고, `/health`, `/docs`, `/api/*` 계약만 제공한다.

## Run

```powershell
uv run python simulator/versions/v2_postgres_react_ops/backend/server.py
```

기본 API 주소:

```text
http://127.0.0.1:8002
```

확인 경로:

```text
GET /          API metadata
GET /health    DB/LLM 설정 상태
GET /docs      OpenAPI UI
```

## Dashboard API

프론트는 아래 `/api` 계약만 기준으로 붙는다.

```text
GET  /api/alerts
GET  /api/alerts/{alert_id}
GET  /api/alerts/events
POST /api/alerts/{alert_id}/ack
POST /api/alerts/{alert_id}/resolve

POST /api/agent-runs
GET  /api/agent-runs/{run_id}
GET  /api/agent-runs/{run_id}/events
GET  /api/agent-runs/{run_id}/artifacts
```

`POST /api/alerts/enqueue`는 local/dev bootstrap용이다.

## Flow

```mermaid
flowchart TD
  A["sensor/model result"] --> B["PostgreSQL"]
  B --> C["priority card / alert"]
  C --> D["GET /api/alerts"]
  D --> E["operator selects alert"]
  E --> F["POST /api/agent-runs"]
  F --> G["simulate now / LangGraph later"]
  G --> H["run result + events + artifacts"]
```

## Structure

```text
backend/
  server.py
  alert_routes.py
  agent_run_routes.py
  repository.py
  queries.py
  schemas.py
  settings.py
  usage.py
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
- 현재 agent run 내부: 기존 simulate wrapper
- 다음 backend 확장: LangGraph, SQL evidence tool, RAG retrieval tool, artifact generation tool

## 데이터 적재 명령

- 기본 적재:
  `uv run python scripts/simulate_predictor_db.py`
- alert queue 포함:
  `uv run python scripts/simulate_predictor_db.py --enqueue-alerts`
- 모델 출력 포함:
  `uv run python scripts/simulate_predictor_db.py --model-run-id <UUID>`
- 기존 데이터 유지:
  `uv run python scripts/simulate_predictor_db.py --append`
