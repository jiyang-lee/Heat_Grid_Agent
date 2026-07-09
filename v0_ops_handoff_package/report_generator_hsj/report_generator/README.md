# Report Generator

HeatGrid 운영보조 시스템의 보고서 생성 모듈입니다.

이 모듈은 LangGraph Agent의 최종 판단 결과, ML priority card, 운영 근거, RAG 보강 근거를 받아 한국지역난방공사 직원 또는 현장관리자가 바로 읽을 수 있는 보고서 JSON과 HTML/PDF 렌더링 입력을 생성하는 것을 목표로 합니다.

## 1단계 목표

이번 단계에서는 구현보다 계약과 기본 구조를 먼저 고정합니다.

- 이상징후 보고서 Generator 구조 정의
- 일간 운영 보고서 Generator 구조 정의
- JSON Schema 배치 구조 정의
- Prompt 배치 구조 정의
- Example JSON 배치 구조 정의
- HTML/PDF 렌더링 가능한 template 구조 정의

## 보고서 종류

### 1. 이상징후 보고서

한국지역난방공사 직원이 프론트 화면에서 확인하는 단건 이상징후 보고서입니다.

주요 목적:

- 특정 `card_id` 또는 priority card에 대한 이상징후 판단 요약
- priority, review_required, 주요 근거, 권장 조치 표시
- work order 발행 여부와 상태 표시
- RAG 및 외부 근거를 `evidence_refs`로 연결

### 2. 일간 운영 보고서

한국지역난방공사 직원이 프론트 화면에서 확인하는 일간 요약 보고서입니다.

주요 목적:

- 하루 동안의 priority card 집계
- urgent/high 항목 요약
- 운영자 검토 필요 항목 수
- work order 발행 현황
- 주요 설비, 지사, 계절/시간대별 운영 신호 요약

### 3. 작업지시서

작업지시서는 현장관리자에게 전달되는 메일 문서입니다.

보고서에는 작업지시서 전문을 포함하지 않습니다.

보고서에는 아래 정보만 포함합니다.

```text
work_order_issued
work_order_id
work_order_summary
work_order_status
evidence_refs
```

## RAG의 역할

RAG는 작업지시서 전용 기능이 아닙니다.

RAG는 보고서, 작업지시서, 운영자 화면에서 공통으로 사용할 수 있는 근거 생성/보강 계층입니다.

예상 RAG 근거:

- 기술 기준서
- 운영 매뉴얼
- 법령 및 규정
- 과거 유사 사례
- Weather API 등 외부 맥락

RAG 결과는 ML priority score를 덮어쓰지 않습니다. 대신 판단 근거를 보강하고 `evidence_refs`로 참조 가능하게 연결합니다.

## 폴더 구조

```text
report_generator/
├─ schemas/
├─ prompts/
├─ templates/
├─ src/
└─ examples/
```

## 폴더 역할

### schemas

보고서 출력 JSON Schema를 둡니다.

예정 파일:

```text
anomaly_report.schema.json
daily_ops_report.schema.json
shared_report_blocks.schema.json
```

### prompts

보고서 생성용 prompt를 둡니다.

예정 파일:

```text
anomaly_report.prompt.md
daily_ops_report.prompt.md
```

### templates

HTML/PDF 렌더링용 template을 둡니다.

예정 파일:

```text
anomaly_report.html
daily_ops_report.html
report.css
```

### src

보고서 생성 로직을 둡니다.

현재 파일:

```text
generate_anomaly_report.py
generate_daily_report.py
report_utils.py
validate_examples.mjs
```

Python generator는 `jsonschema`가 설치된 환경에서는 `jsonschema.Draft7Validator`를 사용하고, 설치되지 않은 로컬 mock 환경에서는 내장 fallback validator로 기본 schema 검증을 수행합니다.

Mock 실행 예시:

```powershell
python .\report_generator\src\generate_anomaly_report.py --mock --output .\outputs\report_generator\anomaly_report.mock.json
python .\report_generator\src\generate_daily_report.py --mock --output .\outputs\report_generator\daily_report.mock.json
```

실제 LLM 호출은 아직 연결하지 않았습니다. 이후 OpenAI API 또는 내부 LLM gateway를 `llm_caller` interface로 주입합니다.

RAG/외부 문맥 로컬 보강 테스트:

```powershell
python .\report_generator_hsj\report_generator\src\generate_anomaly_report.py `
  --input .\v0_ops_handoff_package\input.json `
  --with-rag `
  --enrich-only `
  --output .\report_generator_hsj\outputs\report_generator\anomaly_report.enriched_input.json
```

`--with-rag`는 `HEATGRID_RAG_URL` 또는 `--rag-url`이 있으면 RAG 서버의 `/external-context`를 호출합니다.
둘 다 없으면 현재 프로젝트의 `src/heatgrid_rag` 로컬 검색기를 사용합니다.
`--enrich-only`는 LLM 호출 없이 `external_context`와 `rag_evidence`가 붙은 보고서 입력 JSON만 출력합니다.

### examples

샘플 입력과 샘플 출력을 둡니다.

예정 파일:

```text
anomaly_report.input.example.json
anomaly_report.output.example.json
daily_ops_report.input.example.json
daily_ops_report.output.example.json
```

## 입력 소스

Report Generator는 아래 정보를 입력으로 받을 수 있습니다.

- `raw_context`
- `priority_context`
- `internal_context`
- `external_context`
- LangGraph Agent 최종 output JSON
- work order metadata
- RAG evidence refs

## 출력 원칙

- 보고서 본문은 한국어로 작성합니다.
- schema field name은 영어를 유지합니다.
- 작업지시서 전문은 보고서에 포함하지 않습니다.
- work order 관련 정보는 발행 여부, 요약, 상태, ID, 근거 참조만 포함합니다.
- RAG 근거는 본문에 장문으로 붙이지 않고 `evidence_refs`로 추적 가능하게 연결합니다.
- 운영용 보고서에는 `fault_label`, `fault_event_id`, `validation_labels` 같은 정답 라벨성 필드를 포함하지 않습니다.

## 아직 구현하지 않는 것

1단계에서는 아래 항목을 구현하지 않습니다.

- 실제 LLM 호출
- RAG 검색
- embedding 생성
- vector DB 연결
- PDF 생성 엔진
- 프론트 화면 렌더링
- 메일 발송

## 다음 단계 후보

1. 이상징후 보고서 JSON Schema 작성
2. 일간 운영 보고서 JSON Schema 작성
3. shared block 구조 정의
4. prompt 초안 작성
5. example JSON 작성
6. HTML template 초안 작성
7. schema validation 스크립트 작성
