# HeatGrid RAG/운영 로그/외부 문맥 서비스화

## 목적

월간 리포트와 고장보고서가 완성되기 전까지 현재 프로젝트에서 먼저 고정할 서비스 기반은 다음 세 가지다.

1. PostgreSQL + pgvector 기반 RAG 검색
2. Agent 실행 결과와 검색 근거를 저장하는 운영 로그
3. 세종시 아파트 매핑과 기상청 API 문맥을 지시서 답변에 함께 반영

## 실행 구조

```text
화면 카드/window 선택
→ get_ops_evidence
→ get_external_context
   → 세종 1~31 아파트 매핑 조회
   → 기상청 세종 ASOS 시간자료 조회
   → pgvector 또는 JSONL RAG 검색
→ LLM 답변 생성
→ /ops-log로 실행 로그 저장
→ 화면/알림/지시서 응답
```

## Docker DB

```powershell
docker compose up -d heatgrid-pgvector
```

초기 스키마는 `docker/postgres/init/001_heatgrid_schema.sql`에 있다.

주요 테이블:

- `rag_documents`: 문서 원본 단위
- `rag_chunks`: 검색 청크와 pgvector 임베딩
- `substation_building_context`: 세종 1~31 아파트 가상 매핑
- `ops_agent_runs`: Agent 실행 1회 단위 로그
- `ops_retrieval_hits`: 해당 실행에서 검색된 참고자료 근거
- `ops_tool_calls`: 도구 호출 기록

## 데이터 적재

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\ingest_pgvector.py
```

현재 적재 대상:

- `data/rag_sources/metadata/rag_chunks.jsonl`
- `data/external/substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv`

월간 리포트/고장보고서가 들어오면 기존 RAG 청크 생성 흐름에 넣고, 같은 스크립트로 `rag_chunks`에 추가 적재한다.
문서 적재 원칙은 [13_RAG_DB_DOCUMENT_POLICY.md](./13_RAG_DB_DOCUMENT_POLICY.md)를 따른다.
작업지시서, 월간리포트, 고장보고서 모두 원본을 통째로 DB에 넣지 않고, 필요한 부분만 선별한 curated chunk와 metadata만 검색 DB에 적재한다.

## 기상청 문맥

`KMA_SERVICE_KEY`가 설정되어 있으면 `external_context.weather`에 세종 ASOS 시간자료 요약이 붙는다.

사용 방식:

- 관련 기상 요인이 있으면 지시서 답변에 “당시 외기온/강수/적설/바람 등 운영 부하 맥락”으로 반영
- 기상 요인은 고장 원인 확정 근거로 사용하지 않음
- API 키가 없거나 조회 실패 시 답변 생성은 계속 진행

## 세종 아파트 매핑 문맥

`substation_id`를 기준으로 세종 1~31 아파트 매핑을 붙인다.

답변 반영 방식:

- summary에 대상 단지명 반영
- action_plan에 해당 단지 기계실/열교환실/설비 점검 표현 반영
- caution에 “PreDist-세종 매핑은 가상 매핑”임을 필요한 경우 표시

## 검색 백엔드

`HEATGRID_RAG_BACKEND=auto`이면 pgvector DB가 살아 있을 때 DB 검색을 쓰고, 아니면 기존 JSONL 검색으로 내려간다.

강제 전환:

```powershell
$env:HEATGRID_RAG_BACKEND = "pgvector"
```

로컬 fallback:

```powershell
$env:HEATGRID_RAG_BACKEND = "jsonl"
```

## 운영 품질 확인

비교 화면:

```text
http://127.0.0.1:8011/compare
```

최근 실행 로그 API:

```text
http://127.0.0.1:8011/api/runs
```

품질 기준:

- 내부 모델명/변수명 노출 금지
- RAG, chunk, retrieval 같은 구현 용어 노출 금지
- 대상 단지명 포함
- 기상 요인은 관련 있을 때만 운영 부하 맥락으로 사용
- 고장 원인 단정 금지
- 조치 항목은 현장 점검 순서로 작성
