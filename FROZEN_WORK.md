# frozen-work branch labels

이 문서는 `frozen-work` 브랜치의 소스, 라벨, 관리 정책을 기록합니다.

## Branch labels

공통 라벨:

- `frozen`
- `legacy`
- `do-not-edit`
- `source-preserved`

## Source branches

| Source branch | Source SHA | Role | Frozen status |
| --- | --- | --- | --- |
| `agent1` | `b6c1bfe25c5161462cb5abb03cab71c6906d6b94` | 전처리 및 운영 입력 데이터 계약 | `frozen`, `legacy`, `do-not-edit`, `source-preserved` |
| `agent2` | `ed52ddfc7212e679c6f5d0857f95364617ec8d7d` | 초기 data/docs 및 ML feature 계약 | `frozen`, `legacy`, `do-not-edit`, `source-preserved` |
| `mlmodel1` | `67b29ca0456501175cfda068db9453688cee82ff` | Priority ML 실험 및 모델 전달 패키지 | `frozen`, `legacy`, `do-not-edit`, `source-preserved` |
| `mlmodel2` | `6a440ebc5e646c746493090ef558dea5cd84a28c` | 별도 ML 노트북, export, 타당성 보고 | `frozen`, `legacy`, `do-not-edit`, `source-preserved` |
| `proto` | `28c8eb08bcb9f8cdca58fa909148c06c2f7b790b` | agent, schema, server, frontend 통합 프로토타입 | `frozen`, `legacy`, `do-not-edit`, `source-preserved` |

## Excluded branch

| Branch | Archive SHA | Policy |
| --- | --- | --- |
| `alpha` | `bbd05bbe0800ad9b7f9cf510c5c89d597ae189ea` | `archive/alpha-before-delete` 태그로 복구 기준을 남긴 뒤 브랜치 삭제 |

## Conflict preservation policy

- `.gitignore`는 소스 브랜치들의 제외 규칙을 합집합으로 정리했습니다.
- 최상위 `README.md`는 `frozen-work` 안내용으로 교체했습니다.
- 원본 README는 `docs/legacy/source-readmes/`에 보존했습니다.
- 같은 경로에서 충돌난 파일은 원래 경로에 최신 통합본을 두고, 이전 병합본은 `docs/legacy/branch-overlays/`에 보존했습니다.

## GitHub policy

`frozen-work`, `agent1`, `agent2`, `mlmodel1`, `mlmodel2`, `proto`는 직접 수정하지 않습니다.
GitHub ruleset 또는 branch protection으로 삭제, force push, 직접 push를 제한합니다.
