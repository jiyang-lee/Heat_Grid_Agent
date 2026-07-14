# HeatGrid Agent v3-02 실행 계획

작성일: 2026-07-14
기준 HEAD: `ee0c54d fix(agent-review): harden capture status contracts`
기준 원문: `C:/Users/Admin/Downloads/heatgrid-agent-v3.md`

## 결론

v3-02는 v3-01 위에 바로 얹는 두 번째 PR이다. 범위는 `parent·diagnostic worker 평가 projection`과 `운영자 검토·교정 append API`까지만 잡는다.

이번 단계에서 프런트 본화면까지 크게 만들면 범위가 v3-03과 섞인다. v3-02는 백엔드 계약과 DB 불변성, idempotency, CAS를 먼저 닫고, 프런트에는 다음 단계가 바로 붙을 수 있는 API 형태까지만 확정한다.

## 현재 상태

- v3-01 범위인 baseline, immutable review schema, review snapshot capture/read API는 로컬 `develop2`에 반영되어 있다.
- 로컬 `develop2`는 `origin/develop2`보다 5커밋 앞서 있다. 이 5커밋이 v3-01 계열이다.
- 현재 추가된 주요 API는 `GET /api/agent-runs`와 `GET /api/agent-runs/{run_id}/review`다.
- 기존 DB의 과거 실행은 `legacy_unavailable`로 보이는 것이 정상이다. v3-01 이후 실행부터 snapshot 본문이 생긴다.

## v3-02 목표

1. snapshot을 기준으로 parent와 worker의 상태를 deterministic하게 평가한다.
2. 평가 결과를 조회 가능한 API projection으로 제공한다.
3. 운영자 검토를 append-only 이력으로 저장한다.
4. 승인, 교정, 사람 검토 유지 결정을 idempotency key와 expected version으로 안전하게 처리한다.
5. 원본 snapshot, 원본 agent output, 원본 evidence row는 절대 수정하지 않는다.

## 제외 범위

- v3-03 UI 작업
- 정책 개선 후보 생성
- 승인된 정책 후보의 runtime 반영
- worker 추가 또는 worker 권한 확대
- external search, arbitrary URL, generic HTTP capability 재도입
- 로그인/RBAC
- 기존 보고서/작업지시서 화면 전면 재설계

## PR 단위

브랜치: `codex/agent-v3-02-parent-worker-evaluation`
대상 기준: 최신 v3-01 HEAD에서 분기
권장 커밋:

1. `feat(agent-eval): evaluate parent and diagnostic worker traces`
2. `feat(agent-review): add idempotent operator review workflow`

## 작업 1. 평가 모델과 projection API

### 구현 대상

- `AgentRunEvaluation` 계열 Pydantic 모델 추가
- snapshot 기반 pure evaluator 추가
- `GET /api/agent-run-evaluations` 추가
- 필터: `run_id`, `worker_status`, `parent_handling`, `operator_review_status`, `created_from`, `created_to`, `limit`, `cursor`

### 평가 축

| 축 | 값 |
|---|---|
| worker execution | `not_triggered`, `running`, `completed`, `failed`, `timeout`, `invalid`, `budget_exceeded` |
| citation coverage | `complete`, `partial`, `missing`, `not_applicable` |
| input validity | `valid`, `invalid`, `unavailable` |
| parent handling | `used_as_support`, `invalid`, `unavailable`, `fallback_to_human` |
| evidence completeness | `complete`, `partial`, `missing` |

### 핵심 규칙

- deterministic metric과 운영자 label을 섞지 않는다.
- 실제 정답이 없는 run에 `accurate` 같은 판정을 만들지 않는다.
- unknown citation은 성공으로 치지 않는다.
- worker가 없거나 실패한 경우도 API에서 typed status로 보여야 한다.

### 테스트

- completed worker + valid citation
- timeout worker
- invalid worker input
- budget exceeded
- worker not triggered
- missing/unknown citation
- snapshot unavailable
- legacy unavailable

### 완료 조건

- 모든 worker 상태가 exhaustive하게 평가된다.
- parent handling이 `used_as_support|invalid|unavailable|fallback_to_human` 중 하나로 결정된다.
- `GET /api/agent-run-evaluations`가 200/404/422 경로를 가진다.
- cursor/range validation은 기존 `GET /api/agent-runs`와 같은 방식으로 동작한다.

## 작업 2. 운영자 검토 append API

### 구현 대상

- `POST /api/agent-runs/{run_id}/reviews`
- `GET /api/agent-runs/{run_id}/reviews`
- review repository 추가
- run list/review snapshot 응답에서 최신 review status 반영

### 요청 계약

```json
{
  "expected_review_version": 0,
  "idempotency_key": "operator-session-id-or-generated-key",
  "decision": "approve",
  "reviewer": "ops-manager",
  "reason": "현장 확인 필요 없음",
  "disposition": "normal_observation",
  "evidence_annotations": [],
  "operator_labels": {}
}
```

`decision` 값:

- `approve`
- `correct`
- `keep_human_review`

`disposition` 값:

- `normal_observation`
- `inspection_recommended`
- `urgent_review`

### 교정 요청

`correct`일 때만 structured correction을 받는다.

```json
{
  "corrected_summary": "...",
  "corrected_action_plan": "...",
  "corrected_caution": "..."
}
```

### 핵심 규칙

- 같은 `idempotency_key`는 같은 응답을 반환한다.
- 같은 `expected_review_version`으로 들어온 경쟁 submit은 하나만 성공한다.
- stale version은 409를 반환한다.
- 승인 뒤 재검토도 update가 아니라 새 version append다.
- snapshot과 agent output은 수정하지 않는다.

### 테스트

- 최초 approve 저장
- correct 저장과 correction payload 검증
- keep-human-review 저장
- 같은 idempotency key 재호출
- stale expected version 409
- 경쟁 submit 1개만 성공
- invalid correction 422
- snapshot 불변성 확인

### 완료 조건

- `agent_run_reviews`에 version 순서대로 append된다.
- 최신 review status가 run/evaluation/list API에서 일관되게 보인다.
- duplicate idempotency와 stale version의 동작이 테스트로 고정된다.

## 구현 순서

1. v3-02 브랜치 생성 전 `git status --short --branch`로 dirty 범위 확인
2. 기존 v3-01 테스트 재실행
3. evaluation 모델과 pure evaluator 테스트 먼저 작성
4. evaluation repository/API 구현
5. review submit/history 모델 테스트 작성
6. review repository/API 구현
7. run list와 snapshot 응답에서 최신 review status 연결
8. API smoke로 실제 Postgres 경로 확인
9. v3-03에서 쓸 프런트 계약 메모 남기기

## 검증 명령

```powershell
uv run pytest tests/test_agent_review_routes.py tests/test_agent_review_api_repository.py tests/test_agent_review_capture.py -q
uv run pytest tests/test_agent_run_evaluations.py tests/test_agent_review_submit.py -q
uv run pytest tests/test_agent_review_postgres.py -q
Invoke-RestMethod -Uri 'http://127.0.0.1:8003/api/agent-run-evaluations?limit=5'
```

프런트 계약을 같이 건드리면 추가로 실행한다.

```powershell
npm --prefix frontend run typecheck
npm --prefix frontend run lint
npm --prefix frontend run build
```

## API smoke 시나리오

1. 최신 run 조회: `GET /api/agent-runs?limit=1`
2. snapshot 조회: `GET /api/agent-runs/{run_id}/review`
3. evaluation 조회: `GET /api/agent-run-evaluations?run_id={run_id}`
4. 검토 제출: `POST /api/agent-runs/{run_id}/reviews`
5. 같은 idempotency key로 재제출
6. stale expected version으로 제출해서 409 확인
7. history 조회: `GET /api/agent-runs/{run_id}/reviews`

## v3-03로 넘길 산출물

- review snapshot 타입
- evaluation 타입
- review history 타입
- review submit request/response 타입
- `pending|approved|corrected|keep_human_review` 상태 정의
- `available|unavailable|legacy_unavailable|pending` snapshot 상태 정의
- 409 stale version에 대한 프런트 에러 처리 규칙

## 위험과 대응

| 위험 | 대응 |
|---|---|
| snapshot 없는 기존 run이 많음 | `legacy_unavailable`과 `unavailable`을 평가 API에서도 typed status로 유지 |
| worker metric을 정확도처럼 오해 | API 필드명을 `accuracy`가 아니라 `coverage`, `validity`, `handling` 중심으로 제한 |
| 운영자 교정이 원본 결과를 덮어씀 | correction은 review payload에만 저장하고 원본 output은 immutable로 유지 |
| 중복 제출 | idempotency key unique와 expected version CAS 둘 다 사용 |
| v3-03 UI와 범위 섞임 | v3-02는 API smoke까지만, UI 상세는 별도 PR로 유지 |

## 사용자 실행 판단

지금 사용자가 할 일은 하나다. v3-01을 원격 기준으로 어디에 둘지 먼저 정해야 한다.

- v3-01을 `origin/develop2`에 올릴 거면: 현재 로컬 ahead 5를 PR/merge로 정리한 뒤 v3-02 브랜치를 판다.
- v3-01을 별도 feature branch 기준으로 이어갈 거면: 현재 로컬 HEAD `ee0c54d`에서 바로 `codex/agent-v3-02-parent-worker-evaluation`을 판다.

내 추천은 첫 번째다. v3-02는 DB/API 계약이 추가되므로 v3-01 기준점이 원격에 고정된 뒤 시작하는 편이 충돌과 회귀 확인이 훨씬 적다.
