# v0_minimal_ops

이 버전의 목표는 `card_id` 1개를 기준으로 DB에 있는 운영보조 정보를 묶어 `ops_agent_input`을 만들고 LLM 운영 메모를 생성하는 것이다.

## Flow

```text
card_id 1개
-> raw_context 생성
-> priority_context 생성
-> ops_agent_input.json 생성
-> LLM 호출
-> summary/action_plan/caution 저장
```

## Input

`contracts/ops_agent_input.schema.json`

```text
raw_context
- window
- current_best_sensor_values
  - current-best raw sensor aggregate top N
  - v0 seed N=10
- m1_specialist_features
  - M1 specialist compact13
  - 정확히 13개

priority_context
- card
- priority
  - calculation
- model_signals
- explanation
  - why_reason
  - recommended_action
  - review_required
  - review_reasons[]
```

우선순위 점수와 등급은 `raw_context`가 아니라 `priority_context`에만 둔다.

## Output

`contracts/ops_agent_output.schema.json`

```text
summary
action_plan
caution
```

## DB Tables Used

```text
SUBSTATIONS
FAULT_EVENTS
WINDOWS
FEATURE_META_MAP
WINDOW_FEATURES
MODEL_RUNS
MODEL_OUTPUTS
PRIORITY_DECISIONS
PRIORITY_CARDS
PRIORITY_CARD_REVIEW_REASONS
SENSOR_SUMMARIES
LLM_OPS_NOTES
```

## Excluded In v0

```text
RAG
weather API
원본 raw sensor 시계열 전체 적재
```
