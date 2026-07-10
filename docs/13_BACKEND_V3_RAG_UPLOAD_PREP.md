# backend/v3_rag 업로드 전 정리 메모

## 목적

현재 작업은 `agent/mlmodel`에 올리지 않았던 RAG, 외부 데이터, 기상청 문맥, PostgreSQL/pgvector 검색, 운영 로그 관련 작업물을 `backend/v3_rag` 브랜치에 올리기 위한 준비이다.

`develop2`에는 이미 mlmodel 계열 작업이 병합되어 있고, `backend/v3_rag`도 이후 develop2와 합쳐질 예정이므로 아래 충돌 요인을 미리 정리했다.

## 정리한 충돌 요인

### 1. DB 이름 통일

기존 `backend/v3_rag` 운영 API는 기본 DB를 `heatgrid_ops`로 사용한다.

```text
postgresql+asyncpg://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops
```

RAG/pgvector 작업물도 같은 로컬 DB를 보도록 기본값을 `heatgrid_ops`로 맞췄다.

적용 대상:

- `docker-compose.yml`
- `.env.example`
- `src/heatgrid_rag/pgstore.py`
- `docs/11_SERVICE_RAG_LOGGING_AND_CONTEXT.md`
- `docs/12_AGENT_RAG_CURRENT_HANDOFF.md`

주의: 기존 로컬에서 `heatgrid` DB로 만든 `heatgrid-pgvector` 컨테이너/볼륨을 그대로 쓰면 초기 DB명이 다를 수 있다. 새 브랜치 기준으로 테스트할 때는 `heatgrid_ops_pgdata` 볼륨을 새로 쓰거나, 기존 PostgreSQL에 `heatgrid_ops` DB를 별도로 만들어야 한다.

### 2. Python 의존성 병합

`backend/v3_rag`에는 이미 FastAPI, LangChain, LangGraph, SQLAlchemy, asyncpg 계열 의존성이 있었다. RAG 적재와 pgvector 조회용으로 `psycopg[binary]`만 추가했다.

따라서 `pyproject.toml`은 덮어쓰지 않고 병합해야 한다.

### 3. Agent 외부 문맥 연결

기존 backend agent runner는 `get_ops_evidence`만 가지고 있었고, 프롬프트에도 외부 문맥이 없다고 적혀 있었다. 현재는 아래 도구 흐름이 가능하도록 정리했다.

```text
card_id
-> get_ops_evidence
-> get_external_context
   -> 세종 아파트 매핑
   -> 기상청 시간자료 문맥
   -> 운영 참고자료/RAG 검색
-> summary/action_plan/caution
```

사용자에게 직접 보이는 답변에는 내부 용어를 노출하지 않는다.

노출 금지 예:

```text
RAG, chunk, retrieval, pgvector, PostgreSQL, KMA API, get_ops_evidence, get_external_context, current_best, m1_specialist, fault_group
```

사용자 표현 예:

```text
위험도, 의심 유형, 판단 근거, 점검 항목, 문제 발생 위치, 기상 요인, 운영 참고자료
```

### 4. 세종 매핑 데이터 위치

`backend/v3_rag`에는 이미 프론트 전달용 세종 매핑 파일이 있었다.

```text
frontend/substation_mapping_information/
```

이번 RAG/DB 적재 기준 원천은 아래에도 둔다.

```text
data/external/substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv
```

두 파일은 같은 31행/48컬럼 구조이며 값 차이는 없다. `data/external`은 DB/RAG 적재 기준, `frontend/substation_mapping_information`은 프론트 전달 사본으로 본다.

### 5. raw PDF 포함

RAG 원본 추적성과 재가공 가능성을 위해 raw PDF도 포함한다.

```text
data/rag_sources/raw/
```

실제 검색 적재에는 raw PDF 전체가 아니라 아래 선별 자료와 청크를 사용한다.

```text
data/rag_sources/curated/
data/rag_sources/metadata/rag_chunks.jsonl
```

### 6. 제외 대상

아래는 GitHub 업로드 대상에서 제외한다.

```text
.env
.env.*
data/external/source/
data/weather/cache/
output/rag_server/
output/ops_agent/tmp_*.json
output/ops_agent/token_check/
output/ops_agent/style_check/
output/ops_agent/ops_agent_output_*.json
```

`output/ops_agent/cases/`는 `/compare` 화면 검증용 예시 결과라 남긴다.

## 업로드 전 확인 명령

```powershell
uv lock
.\.venv\Scripts\python.exe -m compileall src simulator\versions\v2_postgres_react_ops\backend scripts
rg -n "실제_키_문자열_또는_노출_의심_패턴" . --glob "!.env" --glob "!data/external/source/**" --glob "!output/rag_server/**"
git status --short
```