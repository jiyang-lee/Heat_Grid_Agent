# HeatGrid 운영 보조 에이전트 저장소

이 저장소는 지역난방 HeatGrid 데이터를 바탕으로 고장 위험을 예측하고, 운영자가 알림을 눌렀을 때 LLM 에이전트가 DB 근거, RAG 참고자료, 기상 맥락을 반영한 작업 지시 결과를 만들 수 있도록 준비한 작업 공간이다.

현재 저장소는 네 가지 축으로 나뉜다.

| 영역 | 역할 |
|---|---|
| 모델 파이프라인 | M1 기준 risk, leadtime, priority score와 agent card를 재현한다. |
| 운영 API 서버 | PostgreSQL에 적재된 예측 알림을 `/api/*` 계약으로 제공하고 LangGraph 스타일 agent run을 실행한다. |
| RAG/외부 맥락 | pgvector 또는 jsonl fallback으로 단지 매핑, 운영 참고자료, 기상 맥락을 조회한다. |
| Vite 프론트 | React + TypeScript 운영 대시보드에서 지도, 알림 큐, agent run, v4 결과 보고서를 표시한다. |
| 문서와 인계 자료 | 모델 범위, 실행 근거, API 계약, 프론트/백엔드 작업 기준을 남긴다. |

## 전체 흐름

```text
실시간 센서 데이터
-> DB 적재
-> 예측 모델 실행
-> 예측 결과 DB 적재
-> alert/card 생성
-> 운영 대시보드 표시
-> 운영자가 알림 선택
-> agent run 생성
-> SQL evidence 조회
-> RAG/단지/기상 참고자료 조회
-> LLM 또는 fallback 작업 지시 생성
-> v4 result/report 조회
-> 운영 콘솔 표시
```

지금 본류 기준은 `develop2`다. `backend/v3_rag`, `backend/v3_langgraph_agent_runner`, `example/HG_f_b_1`, `backend/v4_agent_output_contract`, `frontend/v3_ops_dashboard` 작업이 병합되어 백엔드와 Vite 프론트가 같은 계약으로 연결되어 있다.

## 저장소 구조

| 경로 | 내용 |
|---|---|
| `simulator/` | 운영 시뮬레이션과 PostgreSQL 기반 API 서버. |
| `simulator/versions/v2_postgres_react_ops/backend/` | 알림 큐, agent run, health check, RAG 연결, API route 구현. |
| `frontend/` | Vite + React + TypeScript 운영 대시보드. 지도 관제, 운영 콘솔, agent result 표시를 담당한다. |
| `scripts/` | DB bootstrap, 데이터 적재, 파이프라인 보조 스크립트. |
| `src/third_model/` | M1 모델 파이프라인 패키지 코드. |
| `src/heatgrid_rag/` | RAG 검색, pgvector 연동, 세종 단지 매핑, 운영 로그 보조 코드. |
| `src/heatgrid_weather/` | 기상청 API허브 ASOS 자료를 운영 부하 문맥으로 변환하는 코드. |
| `data/` | 처리 데이터, RAG 선별 자료, 세종 매핑, 기상 샘플. |
| `models/` | 학습된 모델 산출물. |
| `artifacts/` | 모델 메타데이터, gate 입력, 실험 산출물. |
| `output/` | agent card, score, report 등 최종 산출물. |
| `compare/` | 모델 비교와 threshold/weight 근거 notebook. |
| `notebooks/` | 분석 notebook. |
| `docs/` | 모델, 운영, API, 검증 문서. |
| `docs/handoff/` | 인계 문서. |
| `docs/model/` | 모델 범위와 모델 인벤토리. |
| `docs/package/` | 패키지 사용과 구성 문서. |
| `docs/report/` | 의사결정, 검증, 프론트/백엔드 계약 보고서. |
| `docs/contracts/` | 프론트와 백엔드가 공유하는 agent result v4 계약 문서와 예시 JSON. |
| `data/rag_sources/` | raw PDF, 선별 markdown, RAG chunk metadata. |
| `tests/` | 모델 재현성, DB bootstrap, API 계약 테스트. |

## 주요 산출물

| 파일 | 의미 |
|---|---|
| `output/agent_priority_card.csv` | 운영 API와 UI가 우선 참조하는 공식 agent card. |
| `output/agent/m1_agent_priority_card.csv` | 공식 card 복사본. |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 specialist 단독 병렬 evidence card. |
| `output/reports/final_validation_report.md` | 최종 검증 요약. |
| `compare/m1_threshold_weight_rationale_report.ipynb` | threshold, weight, hybrid 선택 근거. |

공식 `priority_score`는 current-best baseline과 M1 specialist 신호를 섞은 운영 우선순위다.

```text
priority_score
= 0.65 * current_best_priority_score
+ 0.35 * m1_specialist_priority_score
```

이 값은 자동 정비 지시가 아니라, 운영자가 어떤 알림을 먼저 살펴볼지 정하는 ranking 신호다.

## API와 프론트 계약

운영 대시보드는 먼저 예측 알림 목록을 보여주고, 운영자가 알림 카드를 누르면 agent run을 시작한다. agent run은 기존 `ops_output.summary/action_plan/caution`도 반환하지만, 현재 프론트의 장기 계약은 `GET /api/agent-runs/{run_id}/result`의 v4 결과다.

| 목적 | API |
|---|---|
| 알림 목록과 상세 | `GET /api/alerts`, `GET /api/alerts/{alert_id}` |
| 알림 상태 변경 | `POST /api/alerts/{alert_id}/ack`, `POST /api/alerts/{alert_id}/resolve` |
| 알림 이벤트 스트림 | `GET /api/alerts/events` |
| 에이전트 실행 시작 | `POST /api/agent-runs` |
| 에이전트 실행 조회 | `GET /api/agent-runs/{run_id}` |
| 에이전트 v4 결과 | `GET /api/agent-runs/{run_id}/result` |
| 에이전트 이벤트와 산출물 | `GET /api/agent-runs/{run_id}/events`, `GET /api/agent-runs/{run_id}/artifacts` |
| 서버 상태 | `GET /health` |

v4 결과 계약은 `docs/contracts/ops_agent_result_v4.md`와 `docs/contracts/ops_agent_result_v4.example.json`을 기준으로 한다. 화면에서는 `headline`, `situation`, `evidence`, `actions`, `cautions`, `report`를 사용한다.

## 로컬 실행

현재 로컬 데모 기준 포트는 다음과 같다.

| 서비스 | 주소 | 비고 |
|---|---|---|
| 백엔드 | `http://127.0.0.1:8003` | FastAPI, PostgreSQL, pgvector/RAG 연결 |
| 프론트 | `http://127.0.0.1:5173` | Vite dev server, `/api`와 `/health`를 백엔드로 프록시 |

백엔드 실행:

```bash
uv run uvicorn --app-dir simulator/versions/v2_postgres_react_ops/backend server:app --host 127.0.0.1 --port 8003
```

프론트 실행:

```bash
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

정상 연결 확인:

```bash
curl http://127.0.0.1:8003/health
curl http://127.0.0.1:5173/health
```

정상 상태 예시는 다음과 같다.

```json
{"input":"postgresql","database":"connected","openai":"configured","rag":"pgvector"}
```

OpenAI 키는 루트 `.env`의 `OPENAI_API_KEY`를 사용한다. 기상청 API 키는 RAG/기상 맥락에서 `KMA_SERVICE_KEY`를 직접 읽는다. `.env`는 커밋하지 않는다.

## 현재 프론트

`frontend/`는 Vite + React + TypeScript 앱이다.

| 화면 | 내용 |
|---|---|
| 지도 관제 | 세종 1생활권 31개 단지 지도와 기계실 상세 화면. |
| 운영 콘솔 | `/api/alerts` 알림 큐, ack/resolve, agent run 실행, SSE timeline, token/cost, v4 작업 지시 결과 표시. |

기본값은 실백엔드 연결이다. mock이 필요하면 `frontend/.env`에 `VITE_USE_MOCK=true`를 둔다. 백엔드 주소를 바꾸려면 `VITE_BACKEND_URL=http://127.0.0.1:<port>`를 사용한다.

## 문서 지도

| 문서 | 내용 |
|---|---|
| `docs/README.md` | 전체 문서 목록과 읽는 순서. |
| `docs/contracts/ops_agent_result_v4.md` | 프론트가 소비하는 agent result v4 계약. |
| `docs/contracts/ops_agent_result_v4.example.json` | v4 결과 예시 JSON. |
| `docs/report/01_frontend_backend_contract_status_ko.md` | 프론트/백엔드 계약, 현재 상태, 다음 작업. |
| `docs/05_RUNBOOK.md` | 실제 실행과 검증 명령. |
| `docs/package/PACKAGE_README_KO.md` | 패키지 사용 안내. |
| `docs/handoff/HANDOFF.md` | 짧은 인계 요약. |
| `docs/handoff/M1_SPECIALIST_HANDOFF_KO.md` | M1 specialist 중심 인계. |
| `docs/model/MODEL_INVENTORY_KO.md` | 모델 파일, score, 재학습 책임. |
| `docs/08_MODEL_REPORT_DEFENSE_AUDIT.md` | 보고서 방어 체크리스트. |

## 현재 작업 기준

`develop2`에 백엔드와 프론트가 모두 합쳐져 있다. 이후 작업은 브랜치를 과하게 쪼개기보다, 공용 작업 브랜치 하나에서 담당 폴더를 나누는 방식이 좋다.

| 담당 | 주 작업 경로 |
|---|---|
| 프론트 | `frontend/**` |
| 백엔드 | `simulator/versions/v2_postgres_react_ops/backend/**`, `src/heatgrid_rag/**`, `src/heatgrid_weather/**` |
| 계약 | `docs/contracts/**`, 필요 시 `tests/**` |

계약이 바뀌는 작업은 먼저 `docs/contracts/ops_agent_result_v4.md`를 바꾸고, 그 다음 백엔드와 프론트를 같은 기준으로 맞춘다.

## 해석 제한

- 현재 검증 범위는 M1이다. M2나 전체 제조사 성능으로 일반화하지 않는다.
- anomaly는 정상 분포 이탈 evidence다. 단독 fault classifier로 설명하지 않는다.
- leadtime은 정확한 고장 시각 예측값이 아니라 priority 참고 신호다.
- priority는 점검 우선순위 ranking 신호이며 자동 정비 지시가 아니다.

실행 명령이 더 필요하면 `docs/05_RUNBOOK.md`를 기준으로 본다. 루트 README는 현재 `develop2`의 역할, 실행 방법, 프론트/백엔드 연결 상태를 빠르게 파악하기 위한 문서다.
