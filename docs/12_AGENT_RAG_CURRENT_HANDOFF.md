# Agent/RAG 현재 구성 및 추후 모델 연동 인수인계

## 현재 구성 요약

현재 프로젝트의 `/compare` 및 RAG 서버는 raw 센서 데이터를 받아 모델을 실시간으로 다시 돌리는 구조가 아니다.

현재는 이미 생성된 모델 산출물인 `output/agent_priority_card.csv`를 기준 입력으로 사용한다. 이 CSV에는 앞단 모델들이 계산한 위험도, 우선순위, 의심 유형, 검토 사유가 들어 있다.

즉 현재 구현 범위는 다음과 같다.

```text
모델 산출물 우선순위 카드(priority card)
→ get_ops_evidence
→ pgvector RAG 검색
→ 세종 아파트 매핑
→ 기상청 API 문맥 결합
→ LLM 답변 생성
→ 운영 로그 저장
→ /compare 화면 표시
```

아직 구현 범위가 아닌 부분은 다음이다.

```text
raw sensor window
→ 전처리
→ anomaly/risk/leadtime/priority/M1 모델 추론
→ 우선순위 카드(priority card) 생성
```

이 부분은 추후 모델 서버 또는 모델 파이프라인 담당자가 붙이면 된다.

## 왜 현재는 CSV 기준인가

현재 `/compare`의 목적은 모델 성능 검증이 아니라 Agent 답변 품질 검증이다.

검증 대상은 다음이다.

- 위험도 산출값이 주어졌을 때 Agent가 운영자 답변을 잘 만드는가
- 운영 참고자료 근거를 자연스럽게 활용하는가
- 세종시 아파트 매핑을 답변에 잘 반영하는가
- 기상청 API 문맥을 고장 원인 단정이 아니라 운영 부하 맥락으로만 사용하는가
- 운영 로그가 남는가
- 사용자가 직접 읽는 문장에 내부 변수명, 모델명, RAG/DB 구현 용어가 노출되지 않는가

따라서 모델 파이프라인 전체를 매번 실행하지 않고, 고정된 모델 산출물 CSV를 입력으로 삼아 Agent/RAG/외부데이터/로그 품질을 안정적으로 검증한다.

## 현재 사용 입력

기본 모델 산출물:

```text
output/agent_priority_card.csv
```

주요 컬럼:

- `substation_id`
- `window_start`
- `window_end`
- `priority_score`
- `priority_level`
- `current_best_priority_level`
- `m1_specialist_fault_group`
- `m1_priority_agreement`
- `review_required`
- `review_reasons`
- `trust_level`
- `why_reason`
- `recommended_action`

현재 Agent는 이 CSV의 한 row를 card/window 단위 입력으로 본다.

## 현재 외부 데이터 결합

### 1. 세종 아파트 매핑

사용 파일:

```text
data/external/substation_buildings_sejong_lifezone1_31_district_heating_context_with_predist.csv
```

현재 `substation_id` 1~31을 세종시 아파트 31개에 가상 매핑한다.

답변에는 다음처럼 반영된다.

```text
문제 발생 위치: 도램마을19단지아파트 (10번 열수급 지점)
```

주의:

```text
세종 아파트와 PreDist 설비의 실제 물리 연결은 검증되지 않은 가상 매핑이다.
```

실서비스 전환 시에는 실제 설비-단지-기계실 매핑 DB로 교체해야 한다.

### 2. 기상청 API

사용 모듈:

```text
src/heatgrid_weather/
```

사용 환경 변수:

```text
KMA_SERVICE_KEY=
```

기상청 API는 모델 CSV의 `window_start`, `window_end` 기준으로 호출한다.

현재 계산 방식:

```text
현재 구간: window_start ~ window_end
비교 구간: window_start-24시간 ~ window_end-24시간
```

답변에는 다음 목적으로만 사용한다.

- 외기온 저하
- 강수
- 적설
- 강풍
- 전일 동시간대 대비 기온 변화
- 난방 부하 증가 가능성

주의:

```text
기상 요인은 고장 원인 확정 근거가 아니라 운영 부하 맥락 보조 근거이다.
```

## 현재 RAG/DB 구성

Docker:

```text
docker-compose.yml
```

DB:

```text
PostgreSQL + pgvector
```

기본 접속:

```text
postgresql://heatgrid:heatgrid@127.0.0.1:55432/heatgrid_ops
```

주요 테이블:

- `rag_documents`
- `rag_chunks`
- `substation_building_context`
- `ops_agent_runs`
- `ops_retrieval_hits`
- `ops_tool_calls`

현재 RAG 청크:

```text
data/rag_sources/metadata/rag_chunks.jsonl
```

DB 적재 명령:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe scripts\ingest_pgvector.py
```

## 현재 서버/API

RAG 서버:

```text
http://127.0.0.1:8011
```

주요 엔드포인트:

- `GET /health`
- `POST /search`
- `POST /external-context`
- `POST /ops-log`
- `GET /api/comparisons`
- `GET /api/runs`
- `GET /compare`

비교 화면:

```text
http://127.0.0.1:8011/compare
```

## 현재 Agent 흐름

검증 스크립트:

```text
v0_ops_handoff_package/scripts/verify_ops_agent_e2e.mjs
```

현재 흐름:

```text
card_id 입력
→ output/agent_priority_card.csv에서 row 선택
→ get_ops_evidence 생성
→ RAG 서버 /external-context 호출
→ 세종 아파트 매핑 + 기상청 문맥 + pgvector 검색 결과 수신
→ OpenAI 모델로 summary/action_plan/caution 생성
→ schema validation
→ output/ops_agent/cases/*.json 저장
→ /ops-log로 운영 로그 저장
```

## 답변 품질 규칙

사용자가 직접 읽는 문장에는 아래 표현을 노출하지 않는다.

- `current_best`
- `m1_specialist`
- `fault_group`
- `RAG`
- `chunk`
- `retrieval`
- `pgvector`
- `PostgreSQL`
- `get_ops_evidence`
- `get_external_context`
- `rag_http_server`
- 내부 모델명
- raw 변수명

사용자에게는 다음 표현으로 바꿔 말한다.

- 위험도
- 의심 유형
- 판단 근거
- 점검 항목
- 문제 발생 위치
- 기상 요인
- 운영 참고자료

또한 `|`, `\`, `1. 1.` 같은 데이터/렌더링 흔적이 답변에 보이지 않도록 후처리한다.

## 추후 모델 서버 연동 방식

추후 다른 작업자가 raw 센서 데이터를 받아 모델을 실시간으로 돌리는 서버를 붙일 경우, 현재 구조를 갈아엎을 필요는 없다.

권장 연동 방식:

```text
raw sensor window
→ 모델 추론 API
→ 우선순위 카드(priority card) JSON 또는 CSV row 생성
→ 현재 Agent/RAG 서버에 전달
→ 기존 external_context/LLM/logging 흐름 재사용
```

현재 `get_ops_evidence(card_id)`는 CSV row를 읽지만, 추후에는 다음 중 하나로 바꾸면 된다.

1. DB에서 `window_id` 기준 우선순위 카드(priority card) 조회
2. 모델 추론 API 응답을 바로 `ops_evidence` 구조로 변환
3. 모델 서버가 생성한 우선순위 카드(priority card)를 PostgreSQL에 저장하고 Agent가 조회

중요한 것은 `ops_evidence` 구조만 유지하는 것이다.

현재 Agent가 기대하는 핵심 구조:

```text
raw_context.window
priority_context.priority
priority_context.model_signals
priority_context.explanation
internal_context.data_quality
expected_output_fields
```

## 실서비스 전환 시 남은 일

- raw sensor window 입력 API 연결
- 모델 추론 API 또는 배치 파이프라인 연결
- 우선순위 카드(priority card) DB 테이블 확정
- 실제 설비-아파트-기계실 매핑 DB로 교체
- 월간 리포트/고장보고서 RAG 문서 추가
- 운영자 피드백 테이블 추가
- 운영 로그 기반 품질 평가 대시보드 추가

## 한 줄 설명

현재 프로젝트는 모델을 실시간으로 다시 돌리는 서버가 아니라, 이미 생성된 모델 산출물 `output/agent_priority_card.csv`를 기준으로 Agent/RAG/세종 매핑/기상청 문맥/운영 로그를 검증하는 서비스화 단계이다. 추후 모델 담당자는 raw window에서 우선순위 카드(priority card)를 생성하는 앞단만 붙이면 된다.
