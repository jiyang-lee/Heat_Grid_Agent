# HeatGrid Agent v3 백엔드 마무리 보고서

작성일: 2026-07-14  
작업 브랜치: `codex/agent-v3-backend-finish`  
기준: `origin/develop2` `053c8b6`

## 결론

v3 남은 작업은 프런트를 건드리지 않고 백엔드 API 중심으로 마무리했다.

- v3-01 snapshot 저장/조회 기반 유지
- v3-02 parent/worker deterministic 평가 API 추가
- 운영자 review append API 추가
- 교정 review 기반 policy candidate API 추가
- 운영 지표 metrics API 추가

`frontend/**`와 `frontend/package*.json`은 수정하지 않았다.

## 추가된 API

| API | 용도 |
|---|---|
| `GET /api/agent-run-evaluations` | snapshot 기준 parent/worker 평가 조회 |
| `POST /api/agent-runs/{run_id}/reviews` | 운영자 승인/교정/사람검토 유지 append |
| `GET /api/agent-runs/{run_id}/reviews` | 운영자 review history 조회 |
| `GET /api/agent-policy-candidates` | 교정 기반 정책 후보 조회 |
| `POST /api/agent-policy-candidates/{candidate_id}/approve` | 정책 후보 승인 |
| `POST /api/agent-policy-candidates/{candidate_id}/reject` | 정책 후보 거절 |
| `GET /api/agent-operations/metrics` | review/worker/policy 후보 운영 지표 조회 |

## 보장한 규칙

- snapshot, agent output, evidence row는 수정하지 않는다.
- review는 `agent_run_reviews`에 append-only로 저장한다.
- review submit은 `expected_review_version`과 `idempotency_key`를 사용한다.
- stale version은 `409`로 응답한다.
- `correct` review만 policy candidate를 만든다.
- approved policy candidate는 v3 runtime에 자동 반영하지 않는다.
- 외부 검색, arbitrary URL, generic HTTP capability는 추가하지 않았다.

## 프런트 인수인계

프런트 담당자는 새 API만 붙이면 된다. 이번 작업에서 프런트 파일은 변경하지 않았으므로, UI 반영은 별도 브랜치에서 진행해야 한다.

필수 UI 연결 지점:

1. 실행 상세에서 `GET /api/agent-run-evaluations?run_id={run_id}` 조회
2. 운영자 action에서 `POST /api/agent-runs/{run_id}/reviews` 호출
3. 검토 이력에서 `GET /api/agent-runs/{run_id}/reviews` 조회
4. 관리자/운영 지표에서 `GET /api/agent-operations/metrics` 조회

## 검증 결과

실행한 검증:

```powershell
uv run pytest tests/test_agent_review_routes.py -q
uv run pytest tests/test_agent_review_routes.py tests/test_agent_review_models.py tests/test_agent_review_migration.py tests/test_agent_review_runner_integration.py -q
uv run ruff check <changed python files>
uv run basedpyright <changed python files>
```

결과:

- route 계약 테스트: `8 passed`
- 관련 review/model/migration/runner 테스트: `38 passed`
- ruff: 통과
- basedpyright: `0 errors`

Postgres 통합 테스트:

- `HEATGRID_V3_REVIEW_TEST_DATABASE_URL`이 설정되지 않아 `tests/test_agent_review_postgres.py`는 skip됨

HTTP smoke:

- 임시 FastAPI 앱을 포트 `8765`에 띄워 `curl`로 다음 endpoint 응답 확인
  - `GET /api/agent-run-evaluations?limit=1`
  - `POST /api/agent-runs/{run_id}/reviews`
  - `GET /api/agent-operations/metrics`

## 남은 제한

- 실제 Postgres DB를 연결한 end-to-end 검증은 아직 필요하다.
- 프런트 UI 연결은 범위에서 제외했다.
- policy candidate 승인 결과는 v3 runtime에 적용되지 않고, v4 정책 반영 입력으로만 남는다.
