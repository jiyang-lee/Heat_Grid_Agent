# RAG/DB 문서 적재 정책

## 목적

이 문서는 HeatGrid Agent에서 RAG와 PostgreSQL/pgvector를 사용할 때 반드시 지켜야 하는 내부 문서 처리 방식입니다.
초기 지시서에서 정한 원칙과 동일하게, 원본 문서를 통째로 검색 DB에 넣지 않습니다.
원본은 보존하고, 실제 검색에는 선별된 근거 chunk만 사용합니다.

## 공통 원칙

1. 원본 문서는 보존용입니다.
   - PDF, 원본 CSV, 원본 문서는 `data/rag_sources/raw/` 또는 별도 source 폴더에 보관합니다.
   - 원본 전체를 그대로 embedding하거나 pgvector에 넣지 않습니다.

2. 검색 DB에는 curated chunk만 넣습니다.
   - 실제 적재 대상은 `data/rag_sources/metadata/rag_chunks.jsonl` 형태의 chunk입니다.
   - 각 chunk는 필요한 부분만 발췌한 `curated_file`에서 만들어져야 합니다.

3. 모든 chunk는 metadata를 가져야 합니다.
   - 필수: `chunk_id`, `document_title`, `source_file`, `curated_file`, `source_type`, `rag_role`, `domain`, `language`, `section_title`, `text`
   - 권장: `page_start`, `page_end`, `extraction_reason`, `download_url`, `fault_type`, `equipment_type`, `output_target`

4. 모델 결과와 문서 근거를 섞지 않습니다.
   - 위험도 점수, 위험도 등급, card/window 정보는 모델/DB 근거입니다.
   - RAG 문서는 설명 보강, 점검 기준, 과거 사례, 운영 맥락을 제공합니다.
   - RAG 문서가 공식 위험도 점수나 등급을 덮어쓰면 안 됩니다.

5. 사용자 출력에는 내부 구현어를 노출하지 않습니다.
   - 금지: `RAG`, `pgvector`, `chunk`, `retrieval`, 함수명, 변수명, 내부 모델명
   - 대신 "운영 기준 근거", "문헌 근거", "과거 사례", "기상 부하 조건"처럼 표현합니다.

## 3가지 산출물 문서 처리 규칙

아래 3종 문서는 모두 같은 내부 방식을 따릅니다.

### 1. 작업지시서

목적:
운영자가 실제 조치로 넘길 수 있는 점검 항목, 담당, 긴급도, 예상 확인 결과를 구조화합니다.

DB/RAG 처리:

- 전문 메일 본문을 그대로 RAG에 넣지 않습니다.
- 설비, 증상, 확인 항목, 조치 기준, 안전 주의, 완료/미완료 상태만 분리합니다.
- `source_type = work_order`
- `rag_role = work_order_procedure`
- `output_target = work_order`

보고서 사용:

- 이상보고서/일간보고서에는 작업지시서 전문을 넣지 않습니다.
- `work_order_summary` 또는 `work_order_overview`에는 metadata만 넣습니다.

### 2. 월간리포트

목적:
계절 부하, 지역 운영 배경, 월별 공급/수요 변화, 반복 이슈를 설명하는 운영 맥락으로 사용합니다.

DB/RAG 처리:

- 월간 리포트 전체를 그대로 넣지 않습니다.
- 기간, 지역, 부하 변화, 주요 반복 이슈, 유지관리 이슈, 운영 주의사항만 추립니다.
- `source_type = monthly_report`
- `rag_role = monthly_ops_context`
- `output_target = anomaly_report` 또는 `daily_ops_report`

보고서 사용:

- 이상 원인 확정 근거가 아니라 운영 배경 설명으로만 사용합니다.
- 예: "해당 월은 난방 부하가 증가하는 기간이라 정상 부하 변화와 이상 신호를 함께 구분해야 합니다."

### 3. 고장보고서

목적:
과거 유사 사례를 기반으로 원인 후보, 확인 항목, 재발 방지 포인트를 보강합니다.

DB/RAG 처리:

- 보고서 전문을 그대로 넣지 않습니다.
- 발생 시점, 설비, 증상, 원인, 조치, 복구 시간, 재발 여부, 예방 대책을 분리합니다.
- 개인정보, 담당자명, 불필요한 내부 결재 문구는 제외합니다.
- `source_type = fault_report`
- `rag_role = fault_case_history`
- `output_target = anomaly_report`, `daily_ops_report`, `fault_report`

보고서 사용:

- 과거 사례는 "유사 사례"로만 표현합니다.
- 현재 건의 원인을 단정하지 않습니다.
- 예: "과거 유사 사례에서는 스트레이너 막힘과 차압 변동이 함께 나타난 바 있어 우선 확인 항목으로 둘 수 있습니다."

## DB 적재 경로

현재 DB 적재는 아래 경로를 사용합니다.

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\ingest_pgvector.py
```

적재 대상:

- `data/rag_sources/metadata/rag_chunks.jsonl`
- `data/external/substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv`

DB 테이블:

- `rag_documents`: 문서 단위 metadata
- `rag_chunks`: 검색 대상 chunk와 vector
- `substation_building_context`: 세종 아파트 가상 매핑
- `ops_agent_runs`: Agent 실행 로그
- `ops_retrieval_hits`: 어떤 chunk가 답변에 사용되었는지 기록
- `ops_tool_calls`: Agent tool 호출 기록

## 코드상 방어선

`scripts/ingest_pgvector.py`는 chunk 적재 전에 아래를 검증합니다.

- 필수 metadata 누락 여부
- 허용되지 않은 `rag_role` 여부
- `curated_file`이 raw 문서가 아닌 curated artifact인지 여부
- 지나치게 큰 chunk 여부
- 작업지시서/월간리포트/고장보고서 chunk의 `source_type`, `rag_role`, `extraction_reason` 적합 여부

이 검증을 통과하지 못하면 pgvector 적재를 중단합니다.

## 현재 상태

현재 들어간 외부 문헌 RAG는 이 정책을 따릅니다.

- 원본 PDF는 `data/rag_sources/raw/`에 보존
- 실제 검색 대상은 `data/rag_sources/metadata/rag_chunks.jsonl`
- manifest에 포함/제외 범위와 chunk 수 기록
- 보고서 프롬프트에서 내부 구현어 노출 금지
- RAG 문서가 모델 위험도 결과를 덮어쓰지 않도록 제한

작업지시서, 월간리포트, 고장보고서 원본이 들어오면 위 규칙으로 curated chunk를 만든 뒤 같은 DB 적재 경로를 사용합니다.
