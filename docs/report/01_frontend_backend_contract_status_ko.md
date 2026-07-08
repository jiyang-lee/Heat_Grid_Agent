# 프론트엔드/백엔드 계약 및 작업 현황

작성 기준: `develop2` 본류 개발, API-only 백엔드 전환 계획.

## 1. 프론트엔드/백엔드 계약 사항

운영대시보드의 기본 흐름은 아래와 같다.

```text
실시간 센서 데이터
-> DB 적재
-> 예측 모델 실행
-> 모델 결과 DB 적재
-> priority card / alert 생성
-> 대시보드 표시
-> 운영자가 alert 클릭
-> agent run 실행
-> LangGraph/RAG/DB tool/artifact 확장
-> 결과와 산출물 표시
```

프론트가 의존하는 정식 계약은 `/api` prefix로 고정한다.

```text
GET  /api/alerts
GET  /api/alerts/{alert_id}
GET  /api/alerts/events
POST /api/alerts/{alert_id}/ack
POST /api/alerts/{alert_id}/resolve

POST /api/agent-runs
GET  /api/agent-runs/{run_id}
GET  /api/agent-runs/{run_id}/events
GET  /api/agent-runs/{run_id}/artifacts
```

`POST /api/alerts/enqueue`는 local/dev bootstrap용이다. 운영 프론트의 일반 사용자 플로우는 alert가 이미 생성되어 있다는 전제에서 시작한다.

프론트가 몰라도 되는 내부 구현은 아래와 같다.

```text
LangGraph node 구성
SQL evidence tool query
RAG retrieval 방식
artifact generation 내부 로직
validation/eval node
fallback 세부 정책
```

## 2. 프론트엔드가 지금까지 한 일 / 앞으로 해야 할 일

지금까지 한 일:

- `frontend/heating_agent.html` 기반 프로토타입 대시보드 작성
- 세종 1생활권 mapping 데이터와 컬럼 사전 정리
- v2 정적 UI로 PostgreSQL card/evidence/stream 흐름을 확인

앞으로 해야 할 일:

- React/Vue/Svelte/Vanilla 등 운영용 스택 선택
- `/api/alerts` 기반 alert feed 화면 구현
- alert detail 패널 구현
- `POST /api/agent-runs` 실행 버튼 연결
- `/api/agent-runs/{run_id}/events` 기반 진행 타임라인 구현
- `/api/agent-runs/{run_id}/artifacts` 기반 산출물 패널 구현
- 백엔드가 늦어질 경우 동일 JSON shape의 mock fixture로 먼저 개발

프론트는 bridge JS나 backend 내부 HTML 서빙에 의존하지 않는다.

## 3. 백엔드가 지금까지 한 일 / 앞으로 해야 할 일

지금까지 한 일:

- fresh PostgreSQL DB bootstrap 보강
- `.env` gitignore 처리
- urgent/high priority card를 alert queue로 적재
- `/api/alerts` 계약 추가
- `/api/agent-runs` 최소 run layer 추가
- OpenAPI에서 프론트 계약 확인 가능하게 정리
- 백엔드를 API-only 서버로 정리

앞으로 해야 할 일:

- agent run 내부를 기존 simulate wrapper에서 LangGraph runner로 교체
- SQL evidence tool 추가
- RAG retrieval tool 추가
- artifact generation tool 추가
- validation/eval node 추가
- run status를 `queued`, `running`, `completed`, `failed`로 확장
- event type을 tool/artifact/validation 단계까지 확장
- artifact metadata와 다운로드/조회 API 확장

현재 API 계약은 내부 구현을 바꿔도 프론트가 `alert_id`, `run_id`, `events`, `artifacts`만 추적하면 되도록 고정하는 것이 목적이다.
