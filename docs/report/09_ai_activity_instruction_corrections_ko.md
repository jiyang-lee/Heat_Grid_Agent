# AI 활동 페이지 구현 지시서 교정 사항

작성일: 2026-07-15
기준 브랜치: develop2
기준 HEAD: `8a5d38b` merge: origin/develop2 — 조원 백엔드(agent-v2/replay/review-chat) 수용

## 개요

바탕화면 지시서(`AI활동_ClaudeCode_구현지시서_수정본.md`, 2026-07-15 `9a493da` 기준 검증본)를 현재 develop2 HEAD `8a5d38b`의 실코드·docs 전수 조사로 재검증했다. 지시서의 핵심 확인 항목은 전부 유효했고, 검증 시점 이후 develop2에 반영된 변경으로 인해 아래 교정이 필요하다. 구현은 이 교정을 반영해 진행한다.

## 유효 재확인된 항목 (지시서 그대로 적용)

| 항목 | 판정 | 근거 |
| --- | --- | --- |
| 목록 응답(`AgentRunListItem`)에 설비/알림/단계/artifact 정보 없음 → additive enrichment 필요 | 유효 | `agent_review_api_models.py` — run_id/status/alert_id/card_id/priority/상태 3종/시각만 |
| 백엔드 포트 정본 8003 | 유효 | settings.py, docker-compose.yml, Dockerfile.backend, vite.config.ts 모두 8003. 8002 없음 |
| `GET /result` 미준비 시 409, run 미존재 404 | 유효 | agent_run_routes.py |
| review 제출 시 `disposition` 필수 | 유효 | `OperatorReviewSubmitRequest` 기본값 없는 Literal 3종 |
| `AgentRunArtifact`에 `created_at` 없음(DB에는 있음) | 유효 | schemas.py |
| 백엔드 `AgentRunResponse`에 `substation_uid` 있음, 프론트 타입 누락 | 유효 | schemas.py:214 vs contracts.ts |

## 교정 사항

### 1. stage 조회 API가 이미 존재한다 (지시서 §2-5, §8)

지시서는 `GET /api/agent-runs/{run_id}/stages`를 "추가가 허용되는 최소 read-only API" 후보로 들었으나, 커밋 `402482a`(feat(agent-observability))가 이미 추가했다. `agent_quality_routes.py`가 노출하는 엔드포인트:

| 엔드포인트 | 내용 |
| --- | --- |
| `GET /api/agent-runs/{run_id}/stages` | StageProjection 목록 — stage_name/attempt/execution_status/quality_status/score/threshold/reasons/retry_exhausted/force_review/`reused_from_snapshot_id`/created_at |
| `GET /api/agent-runs/{run_id}/rerun-lineage` | ancestors/children/requests |
| `GET /api/agent-runs/{run_id}/model-calls`, `/tool-calls`, `/cost-breakdown` | 실행 trace |

→ 실행 단계 표시는 이 API를 사용하며 신규 stages 엔드포인트를 만들지 않는다. 9개 내부 stage(`ml_validation`→`report_fidelity`)를 6개 사용자 단계로 매핑하는 것은 프론트 mapper 한 곳에서 수행한다.

### 2. review decision에 `reject`가 존재한다 (지시서 §2-17, §6)

`OperatorReviewSubmitRequest.decision`은 `approve | reject | correct | keep_human_review` 4값이다(지시서는 3값으로 기술). `reason_category`는 `reject`·`keep_human_review`·`next_action=targeted_rerun`일 때 필수다. 따라서 작업지시서 상세의 `반려` 버튼은 비활성 처리가 아니라 `decision: 'reject'`(+사유·reason_category)로 실제 연결한다.

### 3. 신규 엔드포인트 군 추가 반영 (지시서 §2-7, §8)

지시서 검증 이후 develop2에 추가된 API: review-chat proposal(`POST /api/agent-runs/{run_id}/review-chat/threads`, `POST /api/review-chat/proposals/{id}/confirm` 등), replay(`/api/replay-*`, 기본 feature flag off → 503). 이번 구현 범위에는 review-chat/replay UI가 포함되지 않으며(`docs/report/08` 인계 문서의 후속 범위), proposal 상태머신(`awaiting_confirmation`~`failed`)과 운영자 review 상태(`pending/approved/corrected/keep_human_review`)를 혼동하지 않는다.

### 4. 기준 HEAD 갱신 (지시서 §1)

`9a493da` → `8a5d38b`. 그 사이 변경: 조원 백엔드 19커밋(agent-v2 스테이지 명시화, replay 파이프라인, review-chat proposal, migrations 009~012) + 홈 대시보드 프론트 개편 병합. 조원 커밋은 frontend/를 수정하지 않았다.

### 5. 현황 서술 갱신 (지시서 §2-1, §2-2, §9)

- 사이드바 라벨은 현재 확정적으로 `보고서`다(홈 개편 병합 반영). `AI 활동`으로 변경한다. page key `reports`는 유지.
- `mockViewData.reportRows`/`workColumns`는 이미 어디서도 참조되지 않는 dead export다. "real 화면에 사용 금지"는 유효하며, 정리 대상이다.
- 알림 페이지는 현재 상시 2단 분할(첫 행 자동 선택)이다. "목록 전용 → 선택 시 분할" 패턴은 AI 활동 페이지에서 새로 만든다(`.alert-layout.single`은 존재하지 않음).

### 6. docs 문서 간 모순 판정

| 서술 | 판정 |
| --- | --- |
| `docs/report/02` 본문의 "백엔드 8002 고정" | stale — 같은 문서 상단 정정 메모와 04/05/14 모두 8003 |
| `docs/report/05`의 "v3-02 운영자 검토 append API 미구현" | stale — 06/07/08과 현재 코드에서 구현 완료 |
| stages API 문서 미기재 | 코드(`agent_quality_routes.py`)가 문서보다 앞서 있음 — 본 교정 문서로 보완 |

## 구현에 적용하는 정본 요약

- 화면 데이터 정본: `OpsAgentResultV4`(docs/contracts/ops_agent_result_v4.md) — 보고서 탭=`report{title,format,content}`, 작업지시서 탭=`actions[]`, 근거=`evidence[]`, 주의=`cautions[]`
- 보고서 artifact kind allowlist: `anomaly_report`, `daily_report`
- 사용자 노출 문구에 내부 구현어(RAG/pgvector/chunk/API 키) 금지
- 목록 enrichment·`GET /api/work-orders`·`GET /api/agent-reports`는 additive read-only projection으로 신규 추가(지시서 §8 허용 범위)
