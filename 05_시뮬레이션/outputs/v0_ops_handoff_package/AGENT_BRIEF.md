# Agent Brief

## Task Context

이 패키지는 HeatGrid 운영보조 시뮬레이션 `v0_minimal_ops`의 handoff 산출물입니다.
Obsidian 운영보조 에이전트 노트의 DB 구조를 기준으로 구성했습니다.

## What To Verify

- DB가 Docker Compose로 올라가는지 확인한다.
- `db/schema.sql`과 `db/seed.sql`이 정상 적용되는지 확인한다.
- `input.json`이 v0 입력 계약과 맞는지 확인한다.
- `sensor_summaries`에서 current-best raw sensor aggregate 10개와 M1 specialist compact13 13개가 분리되어 있는지 확인한다.
- priority 점수와 산식이 `priority_context`에만 있는지 확인한다.

## Scope

포함:

- Postgres Docker Compose
- DB schema와 seed SQL
- v0 input JSON
- input/output JSON schema
- 검증 SQL과 실행 스크립트

제외:

- RAG
- 원본 PreDist raw dataset
- 모델 zip 원본
- OpenAI 호출 서버
- 프론트엔드 화면

## Important Contract

`raw_context`에는 우선순위 점수나 등급을 넣지 않습니다.

```text
raw_context.current_best_sensor_values
- current-best 모델 쪽 raw sensor aggregate top N
- v0 seed는 N=10

raw_context.m1_specialist_features
- M1 specialist compact13 feature
- 정확히 13개
```

우선순위 산정값은 `priority_context`에 둡니다.

```text
priority_context
├─ card
├─ priority
│  └─ calculation
├─ model_signals
└─ explanation
   ├─ why_reason
   ├─ recommended_action
   ├─ review_required
   └─ review_reasons[]

priority_score = 0.65 * current_best_priority_score + 0.35 * m1_specialist_priority_score
current_best_priority_score = 100.0
m1_specialist_priority_score = 70.66635910857104
priority_score = 89.73322568799986
priority_level = urgent
```

`priority_context.formula`, root `priority_context.review_reasons`, `priority_context.card.review_required`는 사용하지 않습니다.

## Primary Files

```text
input.json
contracts/ops_agent_input.schema.json
contracts/ops_agent_output.schema.json
db/schema.sql
db/seed.sql
queries/verify.sql
```
