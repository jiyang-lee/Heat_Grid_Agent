# HeatGrid Ops v0 Handoff Package

이 패키지는 v0 운영보조 agent의 입력/출력 계약과 점검용 Postgres seed를 담고 있습니다.

RAG 개발자는 반드시 `RAG_HANDBOOK.md`부터 읽으세요.

현재 범위는 계약 검증과 curated RAG 서버 smoke test입니다. embedding, vector search DB는 포함하지 않습니다.
`scripts/verify_ops_agent_e2e.mjs`는 VSCode/로컬 실행에서 OpenAI API key 기반 최종 output JSON 생성, RAG server context 연결, schema validation을 점검하기 위한 검증 harness입니다.

## 주요 파일

```text
AGENT_BRIEF.md
RAG_HANDBOOK.md
input.json
examples/ops_agent_input.example.json
examples/ops_agent_output.example.json
contracts/ops_agent_input.schema.json
contracts/ops_agent_output.schema.json
db/schema.sql
db/seed.sql
queries/verify.sql
scripts/verify_ops_agent_e2e.mjs
scripts/verify_ops_agent_e2e.ps1
```

## 입력 구조

```text
raw_context
priority_context
internal_context        # optional top-level DB-backed context
```

`raw_context`와 `priority_context`는 운영용 공개 입력으로 유지합니다.
`internal_context`는 optional이며, DB에서 가져온 작은 보강 정보만 담습니다.

기본 운영용 `input.json`에는 `label`, `fault_label`, `fault_event_id`, `estimated_lead_time_hours`처럼 정답 라벨로 보일 수 있는 필드를 넣지 않습니다.

## 출력 구조

최종 LangGraph ReAct 운영보조 agent 출력은 `contracts/ops_agent_output.schema.json` 검증을 통과해야 합니다.

```json
{
  "decision": {
    "priority": "...",
    "operator_review": "...",
    "data_quality": "..."
  },
  "summary": "...",
  "action_plan": ["...", "..."],
  "caution": ["..."],
  "evidence": {
    "priority_score": null,
    "current_best": null,
    "m1_specialist": null,
    "main_signals": [],
    "used_tools": []
  }
}
```

화면 표시 순서:

```text
Decision
Summary
Action Plan
Caution
Evidence
```

UI에서 지원한다면 Evidence는 접기/펼치기 영역으로 표시합니다.

검증 실패 규칙:

```text
출력 JSON이 schema validation에 실패하면 에러를 표시하고 저장하지 않습니다.
```

`get_external_context(card_id)`는 `HEATGRID_RAG_URL`이 있으면 RAG 서버의 `/external-context`를 호출하고, 없으면 현재 프로젝트의 `data/rag_sources/metadata/rag_chunks.jsonl`을 읽어 local curated RAG context를 반환합니다.

## Agent output e2e 검증

OpenAI API key는 코드에 하드코딩하지 않고 루트 `.env` 또는 환경변수의 `OPENAI_API_KEY`에서만 읽습니다.

PowerShell:

```powershell
.\scripts\verify_ops_agent_e2e.ps1 sample-row-1
```

Node 직접 실행:

```powershell
node .\scripts\verify_ops_agent_e2e.mjs sample-row-1
```

검증 스크립트는 현재 프로젝트의 공식 ML 산출물 `output/agent_priority_card.csv`를 기준으로 `get_ops_evidence(card_id)`와 `get_external_context(card_id)`를 단독 점검한 뒤, RAG context를 포함한 OpenAI 호출 결과를 `contracts/ops_agent_output.schema.json`에 맞게 검증합니다.

검증에 성공하면 최종 JSON은 아래 경로에 저장됩니다.

```text
output/ops_agent/ops_agent_output_sample.json
```

## 빠른 검증

PowerShell:

```powershell
.\scripts\verify.ps1
```

Git Bash 또는 Linux/macOS:

```bash
bash ./scripts/verify.sh
```

수동 실행:

```bash
docker compose up -d
docker compose exec -T postgres psql -U heatgrid -d heatgrid_ops < queries/verify.sql
```

기본 DB 접속 정보:

```text
host: 127.0.0.1
port: 55432
database: heatgrid_ops
user: heatgrid
password: heatgrid
```

기대 검증값:

```text
flow1_anomaly_current_best = 10
flow2_m1_specialist = 13
priority_score = 89.73322568799986
priority_level = urgent
current_best_weight = 0.65
m1_specialist_weight = 0.35
```
