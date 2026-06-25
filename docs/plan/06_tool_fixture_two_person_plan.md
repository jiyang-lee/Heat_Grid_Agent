# Tool Fixture 2인 분담: 오전/오후 작업 계획

## Summary
`agent/fixtures/data`의 JSON fixture만 기준으로 작업한다.  
오전에는 변환 툴 2개를 만들고, 오후에는 판단 툴과 `LangChain/LangGraph`를 붙인다.  
목표는 팀원이 같은 fixture를 보면서 역할을 나눠도 흐름이 안 깨지게 하는 것이다.

## Key Changes
- 공통 기준
  - 입력 데이터는 `agent/fixtures/data/*.json`만 사용
  - 새 목업 데이터 추가 없음
  - 실제 PostgreSQL / TimescaleDB 연결 없음
- 오전 작업
  - `ingest_normalize_tool`
    - raw JSON 읽기
    - `raw_event`, `normalized_feature` 생성
  - `predict_adapter_tool`
    - 정규화 결과와 mock ML 데이터를 받아 `prediction` 표준화
- 오후 작업
  - `decision_tool`
    - `prediction`과 `history_context`를 받아 `decision` 생성
  - `LangChain`
    - tool 호출 순서 연결
  - `LangGraph`
    - `START -> ingest -> predict -> decision -> END` 직선 흐름 연결
- 역할 분담
  - A 담당: `ingest_normalize_tool`, `predict_adapter_tool`
  - B 담당: `decision_tool`, `LangChain`, `LangGraph`
- 판단 관련 원칙
  - 오전에는 판단 로직 토론 없음
  - 오후에 decision 규칙을 같이 맞춘 뒤 구현
  - fallback은 이번 범위에서 제외

## Test Plan
- `ingest_normalize_tool`이 raw fixture를 받아 `raw_event`, `normalized_feature`를 만드는지 확인
- `predict_adapter_tool`이 fixture 기반 mock 값을 canonical `prediction`으로 바꾸는지 확인
- `decision_tool`이 `prediction`을 받아 `decision`을 만드는지 확인
- `LangGraph`가 `START -> ingest -> predict -> decision -> END`로 1회 실행되는지 확인
- `normal / anomaly / review / insufficient_data` 케이스가 최소 1개씩 포함되는지 확인

## Assumptions
- fixture JSON은 이미 준비된 `agent/fixtures/data`를 그대로 사용
- tool 구현 시 다른 데이터 소스는 쓰지 않음
- 오후 판단 작업은 `decision_tool`과 graph 연결에 집중
- 최종 합본은 같은 fixture 기준으로 맞춤
