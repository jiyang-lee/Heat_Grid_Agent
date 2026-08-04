# AI 활동 페이지 구현 완료 보고

작성일: 2026-07-15
기준 브랜치: develop2
기준 HEAD: `8a5d38b` merge: origin/develop2 — 조원 백엔드(agent-v2/replay/review-chat) 수용
작업 브랜치: `feat/ai-activity-ui` (push 없음, 로컬 커밋만)

## 개요

사이드바 `보고서`를 `AI 활동`으로 바꾸고, 실행 활동 / 작업지시서 / 보고서 3탭 페이지를 레퍼런스 시안 구조(기본 목록 전용 → 행 선택 시 우측 분할 상세)로 구현했다. 실백엔드(8003, 격리 Postgres 55433)에 연결해 실제 agent run 데이터로 목록·상세·검토 제출까지 검증했다. 지시서 교정 사항은 `docs/report/09_ai_activity_instruction_corrections_ko.md` 참조.

## 변경 파일

| 영역 | 파일 | 역할 |
| --- | --- | --- |
| 백엔드 | `agent_review_api_models.py` | AgentRunListItem additive enrichment 8필드, ListPage total_count, WorkOrder/AgentReport projection 모델 |
| 백엔드 | `agent_run_listing_repository.py` | 목록 lateral join(알림·stage·artifact) 한 방 쿼리, substation_id/search 필터, cursor 제외 total_count |
| 백엔드 | `agent_activity_projection_repository.py` (신규) | `GET /api/work-orders`(result 보유 run), `GET /api/agent-reports`(anomaly/daily report artifact) projection |
| 백엔드 | `agent_review_routes.py` | 목록 파라미터 확장 + 신규 projection 라우트 2개 |
| 백엔드 | `schemas.py`, `agent_run_repository.py`, `agent_run_artifact_repository.py` | AgentRunResponse·AgentRunArtifact에 `created_at` additive 노출 |
| 인프라 | `Dockerfile.backend` | editable 설치(컨테이너 migrate가 /app/migrations를 찾도록) |
| 인프라 | `src/heatgrid_ops/db/migrations.py` | 카탈로그 검증 off-by-one(version<11) — 신규 DB 부트스트랩 불가 버그 수정 |
| 테스트 | `tests/test_agent_activity_projection_routes.py` (신규) | 라우트 7건(enrichment 직렬화·필터 전달·422 커서/날짜·escape_like) |
| 프론트 계약 | `contracts.ts`, `client.ts`, `backend.ts`, `hooks.ts`, `mockApi.ts` | typed 목록 쿼리·stages·projection API·검토 스냅샷 V1 전체 타입·decision reject·mock 패리티+시드 |
| 프론트 화면 | `console/ai-activity/` 9파일 (신규) | AiActivityPage/ActivityFilters/3탭 List·Detail/ReviewActionModal/activityMappers |
| 프론트 | `App.tsx`, `AppShell.tsx`, `operations.css`, `mockViewData.ts` | 라벨 변경, localStorage 자동 복원 제거, 페이지 CSS, dead export 정리 |
| 삭제 | `console/ReportsPage.tsx` | 구 AI 활동 화면(휴리스틱 stepper·세로 스택) 대체 |

## 사용/추가한 API

- 재사용: `GET/POST /api/agent-runs`, `GET .../{id}`, `/result`(409 구분), `/review`, `GET/POST /reviews`, `/iterations`, `/artifacts`, `/artifacts/{id}/content`, `POST /reports/daily`, `GET /agent-runs/{id}/stages`(조원 402482a 신설분 활용)
- 추가(additive read-only): `GET /api/agent-runs`의 `substation_id`/`search`/`total_count`, `GET /api/work-orders`, `GET /api/agent-reports` — 별도 테이블 없이 기존 run/alert/review/artifact projection, N+1 없음(행당 상세 호출 없음)

## 데이터 mapping

- 실행 활동 열: 대상=complexNameOf(substation_id)+기계실 / 연결 알림=priority 배지+enqueue_reason / 시작=run created_at / 현재 단계=stage snapshot→6단계 매핑(ml_validation·weather·rag_retrieval→데이터 수집, rag_interpretation~parent_disposition→AI 판단, report_*→보고서 생성, result 존재→작업지시서 초안, completed→완료; 실패는 실패 단계에서 빨강) / 상태=대기·진행 중·검토 대기(completed+pending)·완료·실패 / 결과=report artifact·result 존재로 표기. **iterations+2 휴리스틱 제거**
- 작업지시서: result(ops_output) 보유 run projection. 상태 mapper: `pending→승인 대기, approved→승인 완료, keep_human_review/corrected→수정 요청(raw는 tooltip 보존, corrected를 승인 완료로 표기하지 않음)`
- 보고서: artifact kind allowlist `anomaly_report/daily_report`. 제목=result.report.title 우선, 파일명 보조. 상태는 위와 동일 mapper(`pending→검토 대기`)
- 판단 근거: 검토 스냅샷 V1(result/decisions/diagnostic 가설/model_verification/weather/evidence internal_rag·operator_manual_evidence/한계) — 없으면 `데이터 없음`, 하드코딩 없음

## 목록 전용 → 분할 → 복원 동작

- 진입/탭 전환 시 목록 전체 폭·자동 선택 없음(localStorage 복원 제거, 알림→실행 생성 딥링크만 1회성)
- 행 클릭/Enter/Space → 우측 분할(1.15fr:0.9fr, sticky), X 닫기/필터로 항목 소실 시 선택 해제·전체 폭 복원
- 1180px 이하에서 상세가 아래로 스택

## 검토 제출과 승인 범위

- `POST /reviews` 계약 전체 준수: disposition 사용자 선택(필수), reject/keep_human_review 시 reason_category 필수, correct 시 corrected_* 3필드, expected_review_version=이력 최신, idempotency_key 모달당 고정, 409 시 이력 재조회 후 재제출 안내
- 승인 subject는 run 전체 — 모달·상세에 "산출물 전체에 적용" 문구 고정 표기
- 성공 시 runs/run/snapshot/reviews/work-orders/agent-reports/정책후보/지표 캐시 무효화

## 검증

| 항목 | 명령/방법 | 결과 |
| --- | --- | --- |
| 백엔드 테스트 | `uv run pytest tests/test_v4_agent_result_contract.py tests/test_agent_activity_projection_routes.py tests/test_agent_review_routes.py tests/test_agent_review_api_repository.py tests/test_database_migration_contract.py -q` (migrator DB URL) | **32 passed** |
| ruff | 변경 백엔드 파일 | 통과 |
| 프론트 | `npm run typecheck` / `lint` / `build` | 3종 통과 |
| DB | 격리 Postgres(55433) 마이그레이션 000~013 + `heatgrid-db-migrate verify` | 통과 |
| 실백엔드 E2E | seed `--append --enqueue-alerts` → `POST /api/agent-runs`로 LLM run 2건 완주 + daily report artifact | 완료 |
| 브라우저(5180, VITE_USE_MOCK=false) | 최초 진입 목록 전용·자동 선택 없음 / 행 선택→분할 / 닫기 복원 / 탭 전환 시 해제 / 열 구성·상태 라벨 / 승인 제출→목록·상세 즉시 '승인 완료' / 1536·1180 반응형·가로 스크롤 없음 | 전부 확인 |

## 한계와 주의점 (백엔드에 없는 기능 — 가짜로 채우지 않음)

- 담당자/연락처/처리 기한/예상 소요 시간/현장 첨부·기록: 계약 없음 → `미지정`/`등록된 파일 없음`/`미연동` 표기
- 체크리스트 완료 저장 API 없음 → 항목만 표시(0/N), 가짜 완료 수 없음
- 보고서 내려받기는 실제 파일 형식(JSON/MD) 표기 — PDF 렌더링 미구현
- 목록 `search`는 서버 ILIKE(알림 사유·manufacturer·run/card ID·보고서명) — 한글 건물명 검색은 건물/기계실 드롭다운(substation_id 필터)으로 제공
- 실행 상태 필터 `완료`는 status=completed 전체(검토 대기 포함 상위집합), `검토 대기`는 정확 매핑
- 알림 enqueue_reason이 기술 문자열(`evaluation_run_id=...;priority_level=...`)로 저장돼 목록에 그대로 노출 — 표시 가공은 데이터 정직성 원칙상 하지 않았고, 백엔드에서 사람이 읽을 사유로 저장하는 개선이 필요
- Review Chat proposal/replay UI는 범위 외(docs/report/08 후속 트랙)
