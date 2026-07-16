# Current RAG Audit

평가 기준 커밋: 로컬 `develop2` 기준 `bb3fb32`  
감사 방식: 서버, Docker, DB 실행 없이 정적 코드와 저장소 문서만 확인했다. API key, 비밀번호, 접속 문자열 원문은 기록하지 않는다.

## 1. 감사 범위와 조사 기준

- 범위: `src/heatgrid_rag`, `src/heatgrid_ops/agent`, `simulator/versions/v2_postgres_react_ops/backend`, `scripts/ingest_pgvector.py`, `scripts/build_rag_curated_corpus.py`, RAG 관련 docs/tests.
- 기준: 최신 pull 이후 현재 로컬 파일만 분석했다. 실제 DB row 수, 서버 health, RAG backend 선택 결과, latency 수치는 실행하지 않았다.
- 확인 상태: 정적 코드상 확인, 문서상 확인, 실행 검증 필요를 구분한다.

## 2. 현재 RAG 전체 아키텍처

- 흐름: curated corpus 생성 -> `rag_chunks.jsonl` -> `scripts/ingest_pgvector.py` -> PostgreSQL/pgvector 또는 JSONL fallback -> `InternalRagEvidenceAdapter` -> `AgentRuntime.external_context_for()` -> agent graph/tool/diagnostic worker.
- 최신 구조 변화: agent runtime이 `RagSearcher`를 직접 소유하던 구조에서 `RagEvidencePort`/`RagEvidenceSnapshot` 포트 구조로 분리됐다.
- 관련 파일: `src/heatgrid_rag/search.py:70`, `src/heatgrid_rag/pgstore.py:63`, `src/heatgrid_ops/agent/ports.py:86`, `src/heatgrid_ops/agent/services.py:46`, `simulator/versions/v2_postgres_react_ops/backend/agent_evidence_adapters.py:18`, `simulator/versions/v2_postgres_react_ops/backend/agent_runtime_factory.py:36`.
- 확인 상태: 정적 코드상 확인.

## 3. 코퍼스 준비 및 원천 문서

- 원칙: 원본 문서 전체를 검색 DB에 넣지 않고, curated chunk만 검색 대상으로 삼는다.
- 현재 metadata 위치: `data/rag_sources/metadata/rag_chunks.jsonl`, `rag_sources_manifest.json`, `ingestion_summary.md`, `test_query_results.md`.
- 관련 파일: `scripts/build_rag_curated_corpus.py`, `docs/13_RAG_DB_DOCUMENT_POLICY.md:12`, `docs/13_RAG_DB_DOCUMENT_POLICY.md:16`.
- 확인 상태: 문서상 확인 및 정적 파일 존재 확인. 원천 문서 품질은 실행/수동 검증 필요.

## 4. 문서 전처리 및 Chunk 생성 구조

- `scripts/build_rag_curated_corpus.py`가 문서별 specification과 chunk 생성 규칙을 가진다.
- 생성 산출물은 curated markdown, manifest, `rag_chunks.jsonl`, `test_query_results.md`이다.
- chunk 생성 결과가 실제 운영 질문에 충분히 맞는지는 수동 relevance 검증이 필요하다.
- 관련 파일: `scripts/build_rag_curated_corpus.py`, `data/rag_sources/metadata/test_query_results.md`.
- 확인 상태: 정적 코드상 확인.

## 5. Chunk Metadata 구조 및 필수 필드

- 필수 필드: `chunk_id`, `document_title`, `source_file`, `curated_file`, `source_type`, `rag_role`, `domain`, `language`, `section_title`, `text`.
- 허용 `rag_role`: `symptom_cause_action_table`, `troubleshooting_manual`, `fault_priority_research`, `domestic_inspection_standard`, `dhc_structure_handbook`, `international_substation_standard`, `work_order_procedure`, `monthly_ops_context`, `fault_case_history`.
- 관련 파일: `scripts/ingest_pgvector.py:28`, `scripts/ingest_pgvector.py:41`, `scripts/ingest_pgvector.py:71`, `docs/13_RAG_DB_DOCUMENT_POLICY.md:20`.
- 확인 상태: 정적 코드상 확인 및 문서상 확인.

## 6. Embedding 방식

- 현재 구현은 OpenAI Embedding 기반 semantic RAG가 아니다.
- `hash_embedding()`이 token hash 기반 1536차원 벡터를 만든다.
- pgvector 적재 시 `document_title`, `section_title`, `text`를 합친 문자열로 hash embedding을 생성한다.
- 검색 query도 같은 hash embedding으로 변환된다.
- 관련 파일: `src/heatgrid_rag/embedding.py:18`, `src/heatgrid_rag/pgstore.py:127`, `scripts/ingest_pgvector.py:202`.
- 확인 상태: 정적 코드상 확인.

## 7. pgvector 적재 및 저장 구조

- 주요 테이블: `rag_documents`, `rag_chunks`, `substation_building_context`, `ops_agent_runs`, `ops_retrieval_hits`, `ops_tool_calls`.
- `ingest_chunks()`는 문서 metadata와 chunk/vector를 upsert한다.
- `review_repository.py`에는 승인된 evidence candidate를 `rag_documents`/`rag_chunks`로 넣는 경로도 있다.
- 관련 파일: `docker/postgres/init/001_heatgrid_schema.sql`, `scripts/ingest_pgvector.py:157`, `scripts/ingest_pgvector.py:258`, `simulator/versions/v2_postgres_react_ops/backend/review_repository.py:257`, `docs/11_SERVICE_RAG_LOGGING_AND_CONTEXT.md:35`.
- 확인 상태: 정적 코드상 확인. 실제 적재 상태는 실행 검증 필요.

## 8. Retrieval 검색 알고리즘

- pgvector 검색은 active `rag_chunks`를 대상으로 `embedding <=> query_embedding` 거리 오름차순 정렬을 사용한다.
- score는 `1 - distance`에 1000을 곱한 값이다.
- metadata filter 없이 `top_k`만 적용한다.
- 관련 파일: `src/heatgrid_rag/pgstore.py:124`.
- 확인 상태: 정적 코드상 확인.

## 9. JSONL Fallback 검색 구조

- pgvector 사용 불가 시 `RagSearcher.search()`가 JSONL chunk를 lexical scoring한다.
- 점수는 term 포함 여부, `rag_role` 가중치, 일부 fault group 특화 가중치로 구성된다.
- 관련 파일: `src/heatgrid_rag/search.py:203`, `src/heatgrid_rag/search.py:251`.
- 확인 상태: 정적 코드상 확인.

## 10. Backend 선택 조건

- `HEATGRID_RAG_BACKEND` 기본값은 `auto`이다.
- `auto` 또는 `pgvector`일 때 `PgVectorStore.available`이 참이면 pgvector를 쓴다.
- `jsonl` 등 다른 값이면 JSONL fallback을 사용한다.
- `available`은 DB 연결과 `rag_chunks`, `substation_building_context` 테이블 존재를 본다.
- 관련 파일: `src/heatgrid_rag/search.py:105`, `src/heatgrid_rag/pgstore.py:69`, `docs/11_SERVICE_RAG_LOGGING_AND_CONTEXT.md:80`.
- 확인 상태: 정적 코드상 확인. 현재 로컬 runtime backend는 실행 검증 필요.

## 11. top_k, metadata filter, synonym 확장, reranker 사용 여부

- `top_k`: 1~20으로 clamp된다. agent 설정 기본은 `rag_top_k = 5`.
- 최신 agent evidence loop에서는 내부 확장 단계에서 `top_k = min(20, rag_top_k + iteration * 3)`로 늘릴 수 있다.
- metadata filter: pgvector/JSONL 검색 모두 hard filter는 없다.
- synonym 확장: `build_terms_from_evidence()`가 fault group 기반 term을 추가한다.
- reranker: 별도 reranker/cross-encoder/LLM reranking은 확인되지 않았다.
- 관련 파일: `src/heatgrid_rag/search.py:133`, `src/heatgrid_rag/search.py:251`, `src/heatgrid_rag/pgstore.py:153`, `src/heatgrid_ops/agent/nodes_evidence.py:142`, `simulator/versions/v2_postgres_react_ops/backend/settings.py:37`.
- 확인 상태: 정적 코드상 확인.

## 12. 검색 결과 반환 JSON 구조

- 검색 반환 구조: `status`, `source`, `backend`, `query`, `top_k`, `chunks`.
- chunk 구조: `chunk_id`, `document_id` 또는 `document_title`, `source_file`, `curated_file`, `rag_role`, `language`, `page_start`, `page_end`, `section_title`, `download_url`, `score`, `matched_terms`, `text`.
- 최신 agent adapter는 검색 결과를 `RagEvidenceSnapshot(status, retrieval, references)`로 감싼다.
- 관련 파일: `src/heatgrid_rag/search.py:251`, `src/heatgrid_rag/search.py:275`, `src/heatgrid_rag/pgstore.py:124`, `src/heatgrid_ops/agent/run_models.py:123`, `simulator/versions/v2_postgres_react_ops/backend/agent_evidence_adapters.py:50`.
- 확인 상태: 정적 코드상 확인.

## 13. Agent와 작업지시서 생성 흐름에서 RAG가 사용되는 위치

- `create_agent_runtime()`가 `InternalRagEvidenceAdapter(RagSearcher())`를 `AgentRuntime.rag`로 주입한다.
- `AgentRuntime.external_context_for()`는 `RagEvidenceRequest`로 RAG를 검색하고, 외부 site/weather snapshot과 합쳐 evidence context를 만든다.
- agent graph는 `get_external_context` node에서 external context를 만들고, 이후 model verification, evidence assessment, output generation으로 전달한다.
- `make_external_context_tool()`와 internal references tool은 LLM tool 경로에서 retrieval/site/weather context를 노출한다.
- diagnostic worker는 retrieval chunk를 `DiagnosticRagChunk`로 변환해 제한된 token budget 안에서 읽기 전용 진단에 사용한다.
- 관련 파일: `simulator/versions/v2_postgres_react_ops/backend/agent_runtime_factory.py:36`, `src/heatgrid_ops/agent/services.py:55`, `src/heatgrid_ops/agent/graph.py:173`, `src/heatgrid_ops/agent/tools.py:68`, `src/heatgrid_ops/agent/tools.py:163`, `src/heatgrid_ops/agent/nodes_diagnostic.py:102`, `src/heatgrid_ops/agent/diagnostic_input.py:27`.
- 확인 상태: 정적 코드상 확인. 최종 답변 반영도는 실행 검증 필요.

## 14. RAG 관련 Logging 구조

- `PgVectorStore.insert_agent_run()`는 `ops_agent_runs`, `ops_retrieval_hits`, `ops_tool_calls`에 기록하는 legacy RAG server logging 경로를 가진다.
- 최신 FastAPI agent run 경로는 `agent_runs.token_usage`, `agent_run_events`, `agent_loop_iterations` 중심으로 강화됐다.
- `ops_retrieval_hits`가 최신 `/api/agent-runs` 실행에서 항상 채워지는지는 정적 코드만으로 확정할 수 없다. `src/heatgrid_rag/server.py`의 `/ops-log` 경로에서는 채워질 수 있다.
- 관련 파일: `src/heatgrid_rag/pgstore.py:206`, `src/heatgrid_rag/pgstore.py:276`, `src/heatgrid_rag/search.py:375`, `src/heatgrid_rag/server.py:598`, `simulator/versions/v2_postgres_react_ops/backend/agent_run_repository.py:42`, `simulator/versions/v2_postgres_react_ops/backend/agent_persistence_adapter.py:74`.
- 확인 상태: 정적 코드상 확인. 최신 agent route와 `ops_retrieval_hits` 연동은 실행 검증 필요.

## 15. 현재 존재하는 테스트 코드와 검증 범위

- RAG core: `PgVectorStore.available`의 필수 테이블 미존재 false 처리 테스트가 있다.
- Agent tool: external context/internal references payload shape 테스트가 있다.
- Port/adapter: `RagEvidencePort`, `InternalRagEvidenceAdapter`, runtime factory 관련 테스트가 추가됐다.
- Diagnostic worker: RAG chunk compaction, citable RAG 부재 시 fallback, token budget 테스트가 있다.
- 없는 것: Recall@K, Precision@K, MRR, nDCG@K, latency, answer grounding, with/without RAG 정량 비교.
- 관련 파일: `tests/test_heatgrid_rag_search.py:41`, `tests/test_heatgrid_ops_agent_tools.py:35`, `tests/test_agent_core_ports.py:18`, `tests/test_diagnostic_input.py:25`, `tests/test_diagnostic_worker.py:66`, `tests/test_v2_postgres_react_ops.py:55`.
- 확인 상태: 정적 코드상 확인.

## 16. 현재 구조의 설계 의도

- 최신 semantic RAG보다 운영 단순성, 의존성 최소화, 재현 가능한 검색, fault group 기반 문서 회수를 우선한다.
- RAG 문서는 모델 위험도 결과를 덮지 않고 설명 보강, 점검 기준, 운영 맥락, 과거 사례 제공에 제한된다.
- 최신 foundation hardening은 agent core를 포트로 분리하고, read-only diagnostic worker로 제한된 근거 기반 진단을 보강하려는 의도가 보인다.
- 관련 파일: `docs/13_RAG_DB_DOCUMENT_POLICY.md:25`, `docs/13_RAG_DB_DOCUMENT_POLICY.md:29`, `docs/15_AGENT_FOUNDATION_HARDENING.md:31`, `src/heatgrid_ops/agent/ports.py:86`.
- 확인 상태: 문서상 확인 및 정적 코드상 확인.

## 17. 현재 구조의 장점

- OpenAI embedding API 없이 검색 가능하다.
- pgvector가 없을 때 JSONL fallback이 있다.
- agent runtime에서 RAG가 포트로 분리되어 비교 실험이나 fake adapter 주입이 쉬워졌다.
- diagnostic worker가 RAG chunk를 token budget 안에서 compact하는 안전장치를 갖는다.
- `agent_run_events`, `agent_loop_iterations`, `token_usage` 경로가 강화되어 agent-level 분석 여지가 커졌다.
- 확인 상태: 정적 코드상 확인.

## 18. 현재 구조의 한계

- `hash_embedding`은 semantic embedding이 아니므로 동의어, 문장 의미, 한국어 표현 다양성에 취약할 수 있다.
- pgvector 검색에는 metadata filter, role/fault filter, reranker가 없다.
- JSONL fallback은 query phrasing과 수작업 가중치에 민감하다.
- relevant chunk label이 없어 Retrieval 지표는 바로 계산할 수 없다.
- retrieval 전용 latency와 retrieval context/result의 일관된 run-level 저장은 부족하다.
- `ops_retrieval_hits`는 존재하지만 최신 agent run 경로에서 항상 채워지는지 실행 검증이 필요하다.
- 확인 상태: 정적 코드상 확인 및 평가 관점 분석.

## 19. 정량평가 시 반드시 측정해야 하는 항목

- Retrieval: Recall@K, Precision@K, MRR, nDCG@K, no_match rate, backend fallback rate, role/fault group별 hit rate.
- Answer: Grounding, Faithfulness, Answer Relevance, Hallucination, Citation Accuracy.
- 시스템: Retrieval Latency, End-to-End Latency, Token Usage, diagnostic worker trigger/fallback rate.
- 비교: with_rag/no_rag, pgvector/JSONL, top_k, hash_embedding/semantic embedding 후보.
- 확인 상태: 평가 설계상 필요.

## 20. 평가 데이터셋 구축 시 필요한 정보

권장 JSONL 구조:

```json
{
  "case_id": "leakage_water_loss_high_001",
  "query": "strainer differential pressure leakage diagnosis",
  "source_input_ref": {"card_id": "...", "alert_id": "..."},
  "fault_group": "leakage_water_loss",
  "priority_level": "high",
  "relevant_chunk_ids": ["danfoss_troubleshooting_table__row001"],
  "relevant_document_ids": ["..."],
  "graded_relevance": {"danfoss_troubleshooting_table__row001": 2},
  "expected_answer_points": ["check strainer differential pressure"],
  "forbidden_claims": ["weather caused the fault"],
  "citation_expectations": [
    {
      "answer_point": "check strainer differential pressure",
      "supporting_chunk_ids": ["danfoss_troubleshooting_table__row001"]
    }
  ],
  "diagnostic_expected": false,
  "split": "dev",
  "label_source": "human"
}
```

- 최소 필요 label: `query`, `relevant_chunk_ids` 또는 `relevant_document_ids`.
- Answer 평가용 추가 label: expected answer points, forbidden claims, citation expectations.
- 최신 구조 추가 label: diagnostic worker가 기대되는 case인지 여부.
- 확인 상태: 평가 설계상 필요.

## 21. 실행 검증이 필요한 항목

- 현재 로컬에서 active backend가 pgvector인지 JSONL인지.
- 실제 `rag_chunks` DB row 수, role별 row 수, index 상태.
- query별 retrieval 결과와 latency.
- 최신 `/api/agent-runs`에서 `ops_retrieval_hits`가 채워지는지.
- `agent_run_events`, `agent_loop_iterations`, `token_usage`가 평가에 충분한지.
- diagnostic worker가 RAG chunk를 실제 답변 품질에 어떻게 반영하는지.
- with_rag/no_rag case file이 현재 로컬에 충분히 존재하는지.
- 확인 상태: 실행 검증 필요.

## 22. 다음 단계 권장 작업

- 1순위: retrieval evaluation JSONL을 만든다. `relevant_chunk_ids`가 있어야 Recall@K, Precision@K, MRR이 열린다.
- 2순위: 동일 query set으로 pgvector/JSONL 결과를 수집한다.
- 3순위: 최신 agent run 경로에서 `retrieval context + final answer + source_input + token_usage + diagnostic_summary`를 함께 저장할 수 있는지 확인한다.
- 4순위: with_rag/no_rag, top_k, backend 비교 실험 계획을 확정한다.
- 확인 상태: 평가 설계 제안.

