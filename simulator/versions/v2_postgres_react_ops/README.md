# v2_postgres_react_ops

`develop2` 기준 PostgreSQL 입력을 읽는 HeatGrid 운영 보조 API 서버다.
이 서버는 프론트 정적 파일을 서빙하지 않고, `/health`, `/docs`, `/api/*` 계약만 제공한다.

## Run

```powershell
uv run python simulator/versions/v2_postgres_react_ops/backend/server.py
```

기본 API 주소:

```text
http://127.0.0.1:8003
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
GET  /api/agent-runs/{run_id}/iterations

GET  /api/review-tasks
POST /api/review-tasks/{task_id}/submit
GET  /api/evidence-candidates
POST /api/evidence-candidates/{candidate_id}/review
GET  /api/automation-policy
PATCH /api/automation-policy
GET  /api/retrain-jobs
POST /api/retrain-jobs
GET  /api/model-candidates
POST /api/model-candidates/{candidate_id}/promote
```

`POST /api/alerts/enqueue`는 local/dev bootstrap용이다.

## Flow

```mermaid
flowchart TD
  A["센서와 예측 결과"] --> B["운영 데이터베이스"]
  B --> C["우선순위 카드와 알림"]
  C --> D["운영자가 알림 선택"]
  D --> E["운영 근거와 내부 자료 조회"]
  E --> F["현재 활성 모델 재검증"]
  F --> G["근거 충족도 판단"]
  G -->|"부족"| H["내부검색 확대·외부 후보·모델 재실행"]
  H --> G
  G -->|"충분 또는 검수 필요"| I["작업 지시 생성"]
  I --> J["최종 사람 검수"]
  J --> K["학습 피드백·재학습·모델 후보"]
  K --> L["최종 승격 후 다음 실행에 반영"]
```

## Structure

```text
backend/
  server.py
  alert_routes.py
  agent_run_routes.py
  repository.py
  automation_routes.py
  review_repository.py
  retrain_routes.py
  retrain_repository.py
  retrain_service.py
  agent_loop_repository.py
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
- 현재 agent run 내부: 제한 재귀 LangGraph, SQL/RAG 근거, 활성 모델 재검증, 최종 검수 작업
- 지도·알림·agent run 공통 기준: 최신 완료 `priority_evaluation_runs`의 31개 Substation 스냅샷
- 기본 freshness 허용 지연: 720시간. stale/missing은 순위와 알림에서 제외
- 재학습: 승인된 피드백으로 후보 모델 생성 후 최종 승격 승인

## 데이터 적재 명령

- 기본 적재:
  `uv run python scripts/simulate_predictor_db.py`
- alert queue 포함:
  `uv run python scripts/simulate_predictor_db.py --enqueue-alerts`
- 모델 출력 포함:
  `uv run python scripts/simulate_predictor_db.py --model-run-id <UUID>`
- 기존 데이터 유지:
  `uv run python scripts/simulate_predictor_db.py --append`
