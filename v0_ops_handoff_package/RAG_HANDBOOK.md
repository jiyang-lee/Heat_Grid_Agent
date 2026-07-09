# HeatGrid RAG Handoff

## 프로젝트 현재 상태

- ML 완료
- Priority Engine 완료
- Input Contract 완료
- Output Contract 완료
- OpenAI API 연결 완료
- get_ops_evidence 구현 완료
- get_external_context local curated RAG 연결 완료

## RAG 개발자가 반드시 읽어야 하는 파일 순서

1. `RAG_HANDBOOK.md`
2. `README.md`
3. `AGENT_BRIEF.md`
4. `contracts/ops_agent_input.schema.json`
5. `contracts/ops_agent_output.schema.json`
6. `input.json`
7. `examples/ops_agent_input.example.json`
8. `examples/ops_agent_output.example.json`
9. `scripts/test_get_external_context.mjs`
10. `scripts/verify_ops_agent_e2e.mjs`
11. `db/schema.sql`
12. `db/seed.sql`
13. `queries/verify.sql`

## 현재 Agent 흐름

```text
card_id

↓

get_ops_evidence(card_id)

↓

PostgreSQL

↓

raw_context
priority_context
internal_context

↓

get_external_context(card_id)

↓

external_context.retrieval.chunks

↓

LLM

↓

Output JSON
```

## 현재 Tool

### 1. get_ops_evidence(card_id)

역할

- Priority Card 조회
- raw_context 생성
- priority_context 생성
- internal_context 생성

수정 금지

- RAG 개발 단계에서는 이 tool의 입력/출력 계약을 바꾸지 않습니다.
- `raw_context`, `priority_context`, `internal_context`의 기존 구조를 변경하지 않습니다.

### 2. get_external_context(card_id)

현재 상태

```json
{
  "status": "configured",
  "retrieval": {
    "status": "available",
    "source": "local_curated_rag_chunks",
    "chunk_file": "data/rag_sources/metadata/rag_chunks.jsonl",
    "top_k": 5,
    "chunks": []
  }
}
```

현재 연결

```text
curated RAG chunks
data/rag_sources/metadata/rag_chunks.jsonl
```

RAG 서버 실행:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m heatgrid_rag.server --host 127.0.0.1 --port 8011
```

v0 e2e에서 RAG 서버 사용:

```powershell
$env:HEATGRID_RAG_URL = "http://127.0.0.1:8011"
node .\v0_ops_handoff_package\scripts\verify_ops_agent_e2e.mjs sample-row-1
```

향후 교체 가능

```text
pgvector / vector search server
Weather API
법령/규정 RAG
```

## RAG 개발자가 수정하거나 교체할 수 있는 부분

- `get_external_context()`
- `external_context JSON`
- Weather API
- Vector Search 또는 Chunk Retrieval

## 수정하면 안 되는 부분

- ML
- Priority Engine
- `input.json` 계약
- output schema
- `get_ops_evidence`

## external_context v0 구조

`raw_context`, `priority_context`, `internal_context`를 건드리지 말고 `external_context`만 확장합니다.

```json
{
  "card_id": "sample-row-1",
  "status": "configured",
  "weather": {
    "status": "not_requested"
  },
  "retrieval": {
    "status": "available",
    "source": "rag_http_server",
    "chunk_file": "data/rag_sources/metadata/rag_chunks.jsonl",
    "query": "...",
    "top_k": 5,
    "chunks": []
  },
  "references": {
    "technical_standards": [],
    "regulations": []
  }
}
```

## RAG 구현 시 지켜야 할 계약

- 최종 출력은 반드시 `contracts/ops_agent_output.schema.json`을 통과해야 합니다.
- `evidence.used_tools`에는 실제 호출된 tool 이름을 넣습니다.
- `get_external_context`가 호출되면 `get_external_context`를 `used_tools`에 포함합니다.
- RAG 서버가 실행되면 `rag_http_server`, local chunk search fallback이 실행되면 `local_rag_chunk_search`를 `used_tools`에 포함합니다.
- RAG 검색 결과는 운영자 판단을 돕는 외부 근거이며, ML priority score를 덮어쓰지 않습니다.
- `fault_label`, `fault_event_id`, `label`, `validation_labels` 같은 정답 라벨성 필드는 운영용 입력 또는 출력에 넣지 않습니다.
- `pre_fault` 같은 학습 라벨 표현은 운영자용 문장에서는 `예측 기반 위험 신호`처럼 표현합니다.

## RAG 확인 명령

get_external_context local RAG 확인:

```powershell
node .\scripts\test_get_external_context.mjs sample-row-1
```

기대 출력:

```json
PASS
{
  "card_id": "sample-row-1",
  "status": "configured",
  "retrieval": {
    "status": "available",
    "top_k": 5
  }
}
```

Agent output e2e 확인:

```powershell
node .\scripts\verify_ops_agent_e2e.mjs sample-row-1
```

성공 시 최종 output JSON은 아래 경로에 저장됩니다.

```text
output/ops_agent/ops_agent_output_sample.json
```

## 전달 ZIP 사용 판단

RAG 담당자에게는 `v0_ops_handoff_package` 전체를 전달하는 것을 권장합니다.

이유

- 계약 문서, 샘플 JSON, schema, DB seed, 검증 스크립트가 서로 연결되어 있습니다.
- RAG 개발자는 `get_external_context`만 확장하더라도 output schema와 `get_ops_evidence` 결과 구조를 함께 확인해야 합니다.
- 일부 파일만 전달하면 priority score, review reason, used_tools 매핑 기준을 놓칠 수 있습니다.

## ZIP에서 제외 가능하지만 기본 포함을 권장하는 파일

- `scripts/verify.sh`: Windows/PowerShell만 사용한다면 제외 가능하지만, 크기가 작아 기본 포함을 권장합니다.
- `docker-compose.yml`, `db/schema.sql`, `db/seed.sql`, `queries/verify.sql`: DB를 직접 띄우지 않는 RAG 담당자에게는 당장 필요 없을 수 있지만, evidence 구조 확인용으로 포함을 권장합니다.
- `examples/ops_agent_output.example.json`: 실제 실행 샘플이 있으면 중복처럼 보일 수 있지만, output 계약 이해를 위해 포함을 권장합니다.

## ZIP에서 제외하지 말아야 할 파일

- `RAG_HANDBOOK.md`
- `README.md`
- `AGENT_BRIEF.md`
- `input.json`
- `contracts/ops_agent_input.schema.json`
- `contracts/ops_agent_output.schema.json`
- `examples/ops_agent_input.example.json`
- `scripts/test_get_external_context.mjs`
- `scripts/verify_ops_agent_e2e.mjs`
