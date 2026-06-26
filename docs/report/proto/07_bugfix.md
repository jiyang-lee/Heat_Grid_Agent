# F. 버그픽스 — 키 충돌 + PK 유니크 — `8c1b3a5`

> 프론트를 띄워 검증하던 중 발견한 실제 버그(중복 key)를 근본 수정한 단계.

![버그픽스 다이어그램](img/07_bugfix.svg)

## 정성 (무엇 / 왜 / 특성)
- **증상**: React 콘솔에 "두 자식이 같은 key" 경고. 행이 누락/중복될 수 있는 실제 결함.
- **근본 원인 (두 겹)**:
  1. 행 키가 `substation_id + window_start`만 써서, **서로 다른 제조사가 같은 기계실·윈도우**를 가지면 충돌 → `/priority/{key}`·`/agent/output/{key}` 라우팅까지 모호.
  2. `generate_mock`이 PK 유니크를 보장하지 않아 동일 `(manufacturer, substation_id, window_start)` **중복 행** 생성.
- **수정**: 공용 `make_key(manufacturer, substation_id, window_start)`로 통일(서버·tools·드래프트 파일명 동일 규칙) + `generate_mock` 유니크 보장 + **검증 게이트에 PK 중복 검사 추가**(재발 방지).
- **특성**: 화면을 실제로 띄워 검증(verify)했기에 정적 리뷰로는 놓치기 쉬운 데이터-키 결함을 잡았다.

## 정량
| 항목 | 수정 전 | 수정 후 |
|---|---|---|
| priority_scores PK 중복 | 다수 | **0** |
| make_key 유니크 | 충돌 | 300개 전부 유니크 |
| 프론트 렌더 | 행 누락/중복 위험 | 50행 누락 없이 렌더 |
| 검증 게이트 | PK 검사 없음 | PK 중복 검사 추가 |
