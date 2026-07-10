# 운영 콘솔 연결 이슈 및 처리 현황

> **develop2-loop 통합 메모:** 이 문서는 `example/HG_f_b_1`에서 수행한 병합 전 검증 기록이다. 현재 통합본은 백엔드 `8003`과 최신 Priority 평가 스냅샷 API를 사용한다. 알림 응답에 포함된 `substation_id`로 단지명을 표시하며 `/cards` enrichment와 관리비·알림 기반 지도 상태 fallback은 반영하지 않았다. 비스트리밍 LLM 토큰 사용량 기록 수정은 재귀 에이전트 호출 경로에 맞춰 반영했다.

작성 기준: `example/HG_f_b_1` 브랜치에서 `develop2` 자료로 백엔드↔프론트 실연결 검증 중 발견.
원칙: **기존 백엔드는 고정, 계약(`/api` 경로)·스키마는 무변경.** 원칙적으로 프론트에서만 대응하되,
토큰/비용 집계(이슈 2)만 사용자 승인 하에 **백엔드 최소 수정**(계약·스키마 무변경, 값만 채움)으로 처리.

관련 문서: [01_frontend_backend_contract_status_ko.md](01_frontend_backend_contract_status_ko.md)

---

## 0. 연결 전제 (참고)

- 백엔드 본체: `simulator/versions/v2_postgres_react_ops/backend/server.py` — **포트 8002 고정**.
- 프론트 dev 프록시 기본 타깃이 8003으로 어긋나 연결이 안 되던 문제를 8002로 정렬(프론트만 수정, 백엔드 무변경).
- 실연결 검증: docker pgvector 기동 → `priority_cards` 1252 / `alerts` 147 적재 → 프론트(5173)→프록시→백엔드(8002)로 `/health`, `/api/alerts`, `POST /api/agent-runs`, `/result` 전부 200.

---

## 1. 운영 콘솔 알림에 건물명이 안 뜸 → 해결됨(프론트 enrichment)

### 증상
운영 콘솔 · 알림 큐의 각 알림 제목이 건물명이 아니라 `priority_level=urgent`로 표시.

### 원인
- 프론트가 알림 제목 자리에 `AlertSummary.enqueue_reason`을 그대로 출력하는데, 백엔드가 이 값을 `"priority_level=urgent"`로 채운다.
- 근본 원인은 **계약 `AlertSummary`에 건물명 필드가 없다**는 것. 알림은 `card_id`(UUID)만 들고 있어 알림 목록만으로는 건물명을 알 수 없다.

### 지도 관제엔 왜 건물명이 나오나 (출처 차이)
| | 지도 관제 · 수리 우선순위 | 운영 콘솔 · 알림 큐 |
|---|---|---|
| 건물명 출처 | 프론트 로컬 static `src/data/complexes.ts` | 실백엔드 `GET /api/alerts`(계약에 이름 필드 없음) |

> 건물명은 두 화면 모두 로컬 `complexes.ts`에서 온다. 지도 관제는 처음부터 로컬 데이터라
> 이름이 있었고, 운영 콘솔은 계약에 이름이 없어 아래 enrichment로 붙였다.

### 처리 (백엔드/계약 무변경, 프론트 전용)
`card_id → substation_id → 건물명` 매핑으로 이름을 붙인다.
- `complexes.ts`의 `id`가 백엔드 `substation_id`와 동일한 조인 키다(예: `10 = 도램마을19단지아파트`).
- 계약 밖 읽기전용 `GET /cards`로 `card_id → substation_id`를 얻어 로컬 단지 데이터로 치환한다.
- 구현:
  - `frontend/src/ops/useBuildingName.ts` — `useBuildingNameResolver()` 훅(`/cards` 1회 조회 후 캐시, `card_id → 건물명`).
  - `AlertFeed.tsx` / `AlertDetail.tsx` — 이름이 있으면 건물명, 없으면 기존처럼 `enqueue_reason`로 degrade.
  - `client.ts`(cardsApi) · `backend.ts`(cardsApi 노출) · `vite.config.ts`(`/cards` 프록시 추가).
- 한계: 한 단지에 시간 윈도우별 알림이 여러 개라 **같은 건물명이 여러 번** 나올 수 있다(정상). mock 모드/백엔드 미기동 시 `/cards` 실패 → 이름 없이 degrade.

> 주의: 이 enrichment는 "운영 콘솔 알림에 이름 라벨을 붙이는 것"이지, 지도 관제의 수리 우선순위와 운영 콘솔 알림을 동일한 리스트로 만드는 것이 아니다(항목 수·정렬 근거가 다름: 31개 static 랭킹 vs 147개 실시간 alert).

---

## 1-b. 지도 관제 우선순위가 모델이 아니라 관리비 단가였음 → 모델 기준으로 교체

### 증상/원인
지도 관제의 색·수리 우선순위·헤더 긴급/주의/정상 카운트가 **실제 모델(에이전트) 결과가 아니라**
프론트 데모 규칙이었다. `src/domain/model.ts`가 실 고장 데이터가 없어 **총관리비 단가(원/㎡)** 를
내림차순 정렬해 상위 6=긴급/다음 9=주의/나머지=정상으로 결정론적 배정하고 있었다(백엔드 미연결).

- 실제 모델 우선순위는 백엔드 `priority_score`(current_best + M1 specialist)이며 운영 콘솔 알림으로만 나오고 있었다.

### 처리 (백엔드/계약 무변경, 프론트 전용)
tier(긴급/주의/정상) **소스만** 백엔드 alert 기반으로 교체하고, 데모는 폴백으로 유지.
- `src/domain/model.ts` — `createModel(tierById)` 팩토리로 tier 소스를 파라미터화(파생 함수 overall/counts/machineStatus/summaryCounts는 그대로). `demoTierById`(관리비 단가)는 폴백.
- `src/domain/ModelProvider.tsx` — 신규. `GET /api/alerts`(priority_level) + `card_id→substation_id` 매핑으로 단지별 tier 생성(urgent alert→긴급, high alert→주의, 없으면 정상). 조인 키: `complexes.ts id === substation_id`. mock/백엔드 미기동/데이터 없음 → 데모로 degrade.
- 소비처(`Header`·`PriorityAside`·`DetailAside`·`RoomSchematic`·`MapView`)를 `useModel()`로 전환. 지도는 `buildComplexFootprints(overall)` + `setData`로 반응형 색 갱신.
- 검증: 데모 6/9/16 → 모델 **8/10/13**(단지별 alert 최고 등급 집계, urgent 8·high 10·정상 13). 지도 색·리스트·헤더 일치, 콘솔 에러 0.

> 한계: 단지 tier는 모델 기반이지만, 어떤 개별 설비가 고장인지(기계실 뷰 machineStatus)는 여전히 시각 프록시다(백엔드 `fault_group`으로 정밀화 가능, 별도 작업). mock 전용 경로(`mockData.ts`·`workOrder.ts`)는 데모 유지.

---

## 2. 토큰/비용이 항상 $0 → 백엔드 최소 수정으로 실제 값 표시 (해결)

> 갱신: 초기에는 "백엔드 고정"으로 $0을 수용했으나, 이후 **백엔드 최소 수정**을 승인받아
> 실제 토큰/비용이 표시되도록 고쳤다. 아래는 원인과 최소 수정 내용.

### 증상
운영 콘솔의 "토큰 · 비용 지표"가 모델 호출 0 / 토큰 0 / 비용 `$0.00000`.

### 원인 (키 문제가 아님)
- 처음엔 `LLM missing_key`(fallback 모드)라 0이 정상이었다.
- 그러나 백엔드를 레포 루트에서 재기동해 `OPENAI_API_KEY`를 로딩(`openai=configured`)하고 `agent_mode=llm`으로 **실제 GPT가 호출되어 진짜 답변이 생성된 뒤에도** 여전히 0이다.
- 진짜 원인: `POST /api/agent-runs`(비스트리밍) 경로의 백엔드 코드가 **LLM 응답의 토큰 수(`usage_metadata`)를 기록하지 않는다.**
  - `src/heatgrid_ops/agent/nodes.py`의 최종 출력 노드는 `token_usage_for()`(도구 payload 글자 수 = `evidence_payload_chars`만 계산)로 usage를 만들고, `generate_llm_output()`의 토큰 메타데이터를 버린다.
  - 실제 토큰 집계 코드는 **스트리밍(`simulate-stream`) 경로에만** 있다(`services.py`의 `stream_events` → `on_chat_model_end`에서 `usage.calls.append(...)`).
- 결론: **키 유무와 무관한 백엔드 집계 누락.** 키를 정확히 넣어도 이 화면 숫자는 오르지 않는다. (실제 OpenAI 비용은 발생함.)
- 참고: 백엔드는 루트 `.env`(또는 환경변수)에서 키를 읽는다. `frontend/.env`에 넣은 `OPENAI_API_KEY`는 Vite 전용(`VITE_` 접두만 유효)이라 백엔드가 읽지 않는다.

### 처리 (백엔드 최소 수정 — 계약·스키마 무변경, 값만 채움)
비스트리밍 LLM 경로가 `usage.calls`에 실제 호출 토큰을 기록하도록만 고쳤다. 스트리밍 경로가
이미 쓰던 `usage_metadata` 해석 로직을 공유해 재사용한다.
- `src/heatgrid_ops/agent/helpers.py` — `usage_metadata → TokenCall` 추출을 `_token_call_from_usage_metadata`로 공통화하고, ainvoke 결과 메시지용 `token_calls_from_messages()` 추가.
- `src/heatgrid_ops/agent/services.py` — `generate_llm_output(..., usage=None)`가 `ainvoke` 결과 메시지의 토큰을 `usage.calls`에 추가. `generate_note`가 usage를 전달.
- `src/heatgrid_ops/agent/nodes.py` — 최종 노드가 usage를 `generate_llm_output`에 전달(이후 `complete_run`의 `usage_with_totals`가 model_calls/토큰/비용 계산).
- 계약(`AgentRunResponse.token_usage`)·스키마·프론트는 무변경. 프론트는 원래대로 `run.token_usage`를 표시할 뿐.
- 검증(LLM 실모드): 이전 `model_calls=0/$0` → **model_calls=3, 총 18,784 토큰(입력 18,203/출력 581), 비용 $0.00486**, 단가 출처 gpt-5.4-mini. 운영 콘솔 "토큰·비용 지표"에 동일 표시.

> fallback 모드(키 없음)는 여전히 0 — LLM 호출이 없으니 정상.

---

## 3. 요약

| 이슈 | 백엔드 무수정으로 처리 | 상태 |
|---|---|---|
| 프록시 포트 8003→8002 | ✅ 프론트만 | 완료 |
| 알림 건물명 | ✅ 프론트 enrichment(`/cards` + `complexes.ts`) | 완료 |
| 지도 우선순위(관리비→모델) | ✅ 프론트 tier 소스 교체(alert 기반, 데모 폴백) | 완료 |
| 토큰/비용 $0 | 백엔드 최소 수정(usage_metadata 기록, 계약 무변경) | 완료 |
