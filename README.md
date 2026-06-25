# HeatGrid_Agent

지역난방 기계실 센서 데이터 기반 이상/고장 판단 Agent 프로젝트.

## 구성

- `data/` — 제조사별 운영 센서 CSV + 라벨/이벤트 파일
  - 대용량이라 git에 커밋하지 않음 (`.gitignore`에서 제외, `data/README.md`만 추적)
- `docs/` — 프로젝트 문서 (`plan` / `report` / `send` / `todo`)

## 개발 환경

- Python **3.12** (`.python-version`)

코드는 이 위에 직접 작성한다.
