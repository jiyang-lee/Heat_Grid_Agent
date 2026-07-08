# HeatGrid 운영 보조 에이전트 저장소

이 저장소는 지역난방 HeatGrid 데이터를 바탕으로 고장 위험을 예측하고, 운영자가 알림을 눌렀을 때 LLM 에이전트가 근거와 조치 초안을 만들 수 있도록 준비한 작업 공간이다.

현재 저장소는 네 가지 축으로 나뉜다.

| 영역 | 역할 |
|---|---|
| 모델 파이프라인 | M1 기준 risk, leadtime, priority score와 agent card를 재현한다. |
| 운영 API 서버 | PostgreSQL에 적재된 예측 알림을 `/api/*` 계약으로 제공하고 agent run을 시작한다. |
| 프론트 프로토타입 | 운영 대시보드 화면과 지도/설비 데이터를 실험한다. |
| 문서와 인계 자료 | 모델 범위, 실행 근거, API 계약, 프론트/백엔드 역할 분리를 남긴다. |

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
-> LangGraph/RAG/SQL evidence/artifact 생성으로 확장
```

지금 본류 기준은 `develop2`다. 데모성 브랜치에서 만들었던 HTML bridge 주입 구조는 본류에 넣지 않고, 백엔드는 API-only 서버로 정리했다. 프론트는 React, Vue, Svelte, Vanilla 등 스택을 나중에 선택해도 되도록 `/api/*` 계약만 맞추면 된다.

## 저장소 구조

| 경로 | 내용 |
|---|---|
| `simulator/` | 운영 시뮬레이션과 PostgreSQL 기반 API 서버. 현재 백엔드는 API-only로 사용한다. |
| `simulator/versions/v2_postgres_react_ops/backend/` | 알림 큐, agent run, health check, API route 구현. |
| `frontend/` | 프론트 프로토타입과 세종 1생활권 지도 데이터. 최종 프론트 스택은 아직 고정하지 않았다. |
| `scripts/` | DB bootstrap, 데이터 적재, 파이프라인 보조 스크립트. |
| `src/third_model/` | M1 모델 파이프라인 패키지 코드. |
| `data/` | 처리 데이터. |
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

운영 대시보드는 먼저 예측 알림 목록을 보여주고, 운영자가 알림 카드를 누르면 agent run을 시작한다.

| 목적 | API |
|---|---|
| 알림 목록과 상세 | `GET /api/alerts`, `GET /api/alerts/{alert_id}` |
| 알림 상태 변경 | `POST /api/alerts/{alert_id}/ack`, `POST /api/alerts/{alert_id}/resolve` |
| 알림 이벤트 스트림 | `GET /api/alerts/events` |
| 에이전트 실행 시작 | `POST /api/agent-runs` |
| 에이전트 실행 조회 | `GET /api/agent-runs/{run_id}` |
| 에이전트 이벤트와 산출물 | `GET /api/agent-runs/{run_id}/events`, `GET /api/agent-runs/{run_id}/artifacts` |

프론트/백엔드 역할과 앞으로의 작업 범위는 `docs/report/01_frontend_backend_contract_status_ko.md`에 정리되어 있다.

## 문서 지도

| 문서 | 내용 |
|---|---|
| `docs/README.md` | 전체 문서 목록과 읽는 순서. |
| `docs/report/01_frontend_backend_contract_status_ko.md` | 프론트/백엔드 계약, 현재 상태, 다음 작업. |
| `docs/05_RUNBOOK.md` | 실제 실행과 검증 명령. |
| `docs/package/PACKAGE_README_KO.md` | 패키지 사용 안내. |
| `docs/handoff/HANDOFF.md` | 짧은 인계 요약. |
| `docs/handoff/M1_SPECIALIST_HANDOFF_KO.md` | M1 specialist 중심 인계. |
| `docs/model/MODEL_INVENTORY_KO.md` | 모델 파일, score, 재학습 책임. |
| `docs/08_MODEL_REPORT_DEFENSE_AUDIT.md` | 보고서 방어 체크리스트. |

## 개발 브랜치 흐름

| 브랜치 | 용도 |
|---|---|
| `develop2` | 본류 개발 기준. |
| `backend/v3_langgraph_agent_runner` | LangGraph, RAG, SQL evidence tool, artifact generation 확장 작업. |
| `frontend/v3_ops_dashboard` | 운영 대시보드 프론트 작업. 스택은 프론트 담당자가 선택한다. |
| `example/HG_f_b_1` | 필요할 때만 시연용으로 갱신하는 데모 브랜치. |

## 해석 제한

- 현재 검증 범위는 M1이다. M2나 전체 제조사 성능으로 일반화하지 않는다.
- anomaly는 정상 분포 이탈 evidence다. 단독 fault classifier로 설명하지 않는다.
- leadtime은 정확한 고장 시각 예측값이 아니라 priority 참고 신호다.
- priority는 점검 우선순위 ranking 신호이며 자동 정비 지시가 아니다.

실행 명령이 필요하면 `docs/05_RUNBOOK.md`를 기준으로 본다. 루트 README는 저장소의 역할과 구성을 빠르게 파악하기 위한 문서다.
