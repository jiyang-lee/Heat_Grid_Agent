# HeatGrid Agent Foundation v2 검증·GitHub 보고서

## GitHub

- PR #17: merged, `4ba77af`
- PR #18: merged, `c5b1a9e`
- PR #19: merged, `6eb492f`
- PR #20: merged, `fc1b812`
- PR 05: `codex/agent-foundation-05-hardening`, 자체 diff 감사와 gate 후 squash merge

GitHub는 PR 작성자의 자기 승인을 허용하지 않는다. 각 PR은 변경 diff 감사, 집중 테스트, smoke를 통과한 뒤 작성자가 직접 merge했다.

## 검증 결과

| 검증 | 결과 |
|---|---|
| baseline `0f9afa9` 대표 판단 3개 | 3 passed |
| golden field 비교 | passed |
| worker A/B/C, budget, fallback | passed |
| 검색 제거 schema/policy 회귀 | passed |
| clean DB `001~004` fresh 적용 | passed |
| clean DB base 준비 후 `002/004` 재적용 | passed |
| existing DB `004` 2회 적용 | passed |
| existing run backfill 중복 방지 | task count 1 |
| task/ledger/FK/UNIQUE/API columns | present |
| clean HTTP agent run | completed, fallback, final review 1 |
| existing run API | HTTP 200 |
| forced lifespan stop 후 reclaim task | queued, task count 1 |

PR 04 API E2E는 현재 운영 seed에 open alert가 0개여서 입력 준비 단계에서 중단됐다. 계획의 30분·1회 원칙에 따라 seed 복구를 반복하지 않았고, fake-port graph smoke와 실제 PostgreSQL child ledger smoke(`settled|4000|780|1|0`)로 변경 경로를 검증했다.

전체 `uv run pytest -q`는 모든 Foundation PR worktree에서 동일하게 `tests/test_agent_contract.py`의 `from src.third_model import config` collection 오류가 재현된다. 변경 범위 집중 suite, Ruff, basedpyright는 별도 통과 여부를 PR 본문에 기록한다.
