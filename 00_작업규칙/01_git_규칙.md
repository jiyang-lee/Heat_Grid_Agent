# Git 규칙

이 저장소는 `C:\3rd_Project\HeatGridAgent`의 Git 규칙을 따른다.

## 브랜치

- `main`에는 안정된 코드와 검증된 문서만 둔다.
- 기능 개발은 별도 작업 브랜치에서 진행한다.

## 커밋 메시지

커밋 메시지는 한국어 Conventional Commit 형식을 사용한다.

| prefix | 용도 | 예시 |
|---|---|---|
| `feat:` | 기능 추가 | `feat: 시뮬레이션 화면 MVP 추가` |
| `fix:` | 오류 수정 | `fix: JSON 입력 검증 누락 수정` |
| `docs:` | 문서 수정 | `docs: 보고서 작성 규칙 추가` |
| `refactor:` | 구조 개선 | `refactor: 화면 렌더링 로직 분리` |
| `test:` | 테스트 추가/수정 | `test: 시뮬레이션 입력 스키마 검증 추가` |
| `chore:` | 환경/정리 작업 | `chore: 번호 폴더 구조 설정` |

## Git 제외 대상

- `.env`, API key, DB URL, 비밀번호
- `.venv`, `.pytest_cache`, `__pycache__`, `.ipynb_checkpoints`
- 원본 대용량 데이터셋 zip
- 모델 파일과 handoff zip
- 임시 실험 파일

## 작업 기준

- 관련 작업만 staging한다.
- 사용자 요청 없이 원격 push, 배포, 대규모 삭제를 하지 않는다.
- 원본 데이터와 모델 산출물은 Git에 올릴지 먼저 확인한다.
