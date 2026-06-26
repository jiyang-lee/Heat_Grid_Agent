# A. Priority 계약 + 목 데이터 — `04b5d41`

> priority 단계의 입력/출력/라벨을 잠그고, 데모 구동용 목 데이터와 자동 검증 게이트를 만든 단계.

![계약·목데이터 다이어그램](img/02_contract.svg)

## 정성 (무엇 / 왜 / 특성)
- **무엇**: priority 입력·출력·라벨을 기존 schema 패턴(JSON Schema 2020-12 + Postgres DDL)으로 **계약화**했고, Codex 대역 생성기로 목 데이터를 만들었다. 모든 계약은 `validate_contracts`가 통과를 강제한다.
- **왜**: 계약을 먼저 잠가야 모델·에이전트·서버가 같은 스키마로 안전하게 붙는다. 컬럼명은 mlmodel1 ML output 계약과 1:1로 맞춰 실데이터 전환 시 경로만 바꾸면 되게 했다.
- **특성**: `006_priority_scores.sql`은 agent1의 `005` 다음 번호로 자연 연결. priority_level 밴딩은 운영 엔진과 동일하게 urgent/high/medium/low.

## 정량
| 항목 | 값 |
|---|---|
| 계약 파일 | `006_priority_scores.sql`, `priority_scores.schema.json`, `data/mock/README.md` |
| 입력 피처 | 7 (anomaly·risk·leadtime 계열) |
| 라벨 | 정상 0 / 3-7d 33 / 1-3d 66 / 0-24h 100 |
| 목 데이터 | 300행 × 25컬럼, 제조사 2 · 기계실 18 |
| 라벨 분포 | 정상 161 / 고장전조 139 |
| 고장전조 버킷 | 0-24h 65 · 1-3d 39 · 3-7d 35 |
| risk_level 분포 | low 161 · high 114 · critical 23 · medium 2 |
| 검증 게이트 | JSON Schema **6 OK** · DDL **7 OK** · PK 유니크 OK |
