# HeatGrid Agent frozen-work

이 브랜치는 HeatGrid Agent의 레거시 작업물을 보존하기 위한 동결 브랜치입니다.

## 상태

- 라벨: `frozen`, `legacy`, `do-not-edit`, `source-preserved`
- 기준 브랜치: `main`
- 통합 대상: `agent1`, `agent2`, `mlmodel1`, `mlmodel2`, `proto`
- 제외 대상: `alpha`

## 사용 규칙

이 브랜치는 새 기능 개발이나 수정 작업을 위한 브랜치가 아닙니다.
기존 작업물의 보존, 비교, 회고, 인수인계 용도로만 사용합니다.

수정이 필요하면 새 작업 브랜치를 만들고, 이 브랜치에는 직접 push하지 않습니다.

## 보존 위치

- 브랜치별 원본 README: `docs/legacy/source-readmes/`
- 같은 경로에서 충돌난 보존본: `docs/legacy/branch-overlays/`
- 동결 상세 라벨과 SHA: `FROZEN_WORK.md`

## GitHub 관리

GitHub에서는 이 브랜치와 원본 작업 브랜치에 ruleset 또는 branch protection을 적용해
삭제, force push, 직접 push를 막는 것을 기본 정책으로 둡니다.
