# Real Retrieval Connection Audit

검증 방식: 정적 코드 확인. 서버, Docker, DB, ingest는 실행하지 않았다. 민감한 환경변수 값은 출력하지 않았다.

## 1. RagSearcher 초기화 방법

- 파일: `src/heatgrid_rag/search.py`
- 클래스: `RagSearcher`
- 초기화: `RagSearcher(chunks_path=DEFAULT_CHUNKS_PATH, site_context_path=DEFAULT_SITE_CONTEXT_PATH)`
- 기본 chunk 경로: `data/rag_sources/metadata/rag_chunks.jsonl`
- 확인 상태: 정적 코드상 확인

## 2. `RagSearcher.search(...)` signature

```python
search(self, query: str, top_k: int = 5, evidence: dict[str, Any] | None = None) -> dict[str, Any]
```

- `top_k`는 1~20으로 clamp된다.
- 확인 상태: 정적 코드상 확인

## 3. 검색 입력에 필요한 값

- 필수: `query`
- 선택: `top_k`, `evidence`
- `fault_group`, `substation_context`, `query_intent`, `category`는 search signature가 직접 받지 않는다.
- 평가 adapter는 이 값을 `evidence.evaluation_metadata` 및 `priority_context.model_signals.m1_specialist_fault_group`에 담아 전달한다.
- 확인 상태: 정적 코드상 확인

## 4. 검색 결과 item shape

`RagSearcher.search()` 반환:

- `status`
- `source`
- `backend`
- `query`
- `top_k`
- `chunks`

각 chunk는 JSONL backend 기준 `chunk_id`, `document_title`, `source_file`, `curated_file`, `rag_role`, `language`, `page_start`, `page_end`, `section_title`, `download_url`, `score`, `matched_terms`, `text`를 포함한다.

pgvector backend는 `chunk_id`, `document_id`, `document_title`, `source_file`, `curated_file`, `rag_role`, `language`, `page_start`, `page_end`, `section_title`, `download_url`, `equipment_type`, `fault_type`, `risk_level`, `score`, `matched_terms`, `text`를 포함한다.

- 확인 상태: 정적 코드상 확인

## 5. chunk_id 반환 필드

- 필드명: `chunk_id`
- document_id를 chunk_id 대체값으로 사용하지 않는다.
- chunk_id 없는 결과는 평가 adapter에서 warning으로 남기고 제외한다.
- 확인 상태: 정적 코드상 확인

## 6. Backend 선택 조건

- `HEATGRID_RAG_BACKEND`가 `auto` 또는 `pgvector`이면 `PgVectorStore.available`이 true일 때 pgvector를 사용한다.
- 그 외 값, 예를 들어 `jsonl`, 에서는 pgvector store를 만들지 않고 JSONL fallback을 사용한다.
- `search()`는 `self.pg_store is not None`이면 pgvector, 아니면 JSONL을 사용한다.
- 확인 상태: 정적 코드상 확인

## 7. pgvector 사용에 필요한 환경변수와 서비스

- DB URL은 `HEATGRID_DATABASE_URL`, `DATABASE_URL`, 또는 기본값을 사용한다.
- pgvector 사용에는 `psycopg` import 가능 여부와 PostgreSQL 접속, `rag_chunks`, `substation_building_context` 테이블 존재가 필요하다.
- DB 접속 문자열 원문은 출력하지 않는다.
- 실제 DB 서비스 준비 여부: 실행 검증 필요

## 8. JSONL fallback 작동 조건

- `data/rag_sources/metadata/rag_chunks.jsonl`가 존재하면 서버/DB 없이 작동 가능하다.
- `HEATGRID_RAG_BACKEND=jsonl`이면 pgvector를 시도하지 않는다.
- 확인 상태: 정적 코드상 확인

## 9. top_k 전달 방식

- 평가 adapter는 dataset case마다 동일한 `top_k`를 `RagSearcher.search(query=..., top_k=...)`로 전달한다.
- 현재 config 기본값은 `5`다.
- 확인 상태: 정적 코드상 확인

## 10. 외부 의존성

- JSONL backend: 로컬 JSONL 파일만 필요하다.
- pgvector backend: `psycopg`, PostgreSQL, pgvector schema/data가 필요하다.
- weather/API는 `search()` 경로에서 호출하지 않는다.
- 확인 상태: 정적 코드상 확인

## 11. 실행 확인 결과

- `HEATGRID_RAG_BACKEND=jsonl` 기준 `RagSearcher.health()`는 `active_backend=jsonl`, `chunk_count=90`을 반환했다.
- JSONL backend는 28개 review case 전체에 대해 실행 완료했다.
- `HEATGRID_RAG_BACKEND=pgvector` 기준 초기화 시 `active_backend=jsonl`로 남아 pgvector가 활성화되지 않았다.
- pgvector 평가는 DB/service/ingest를 자동 실행하지 않는 원칙에 따라 skip했다.
- 확인 상태: 실행 검증 완료(JSONL), 실행 불가 사유 확인(pgvector).
