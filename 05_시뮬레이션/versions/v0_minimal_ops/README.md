# v0_minimal_ops

이 버전의 목표는 `card_id` 1개를 기준으로 DB에 있는 최소 정보만 묶어 ops agent를 한 번 호출하는 것이다.

## Scope

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
- features

priority_context
- card
- priority
- model_signals
- explanation
```

## Output

`contracts/ops_agent_output.schema.json`

```text
summary
action_plan
caution
```

## DB Tables Used

```text
WINDOWS
WINDOW_FEATURES
SUBSTATIONS
PRIORITY_CARDS
PRIORITY_DECISIONS
LLM_OPS_NOTES
```

## Excluded In v0

```text
SENSOR_SUMMARIES table
direction calculation
summary_text generation
weather API
RAG
```

`source_sensor`와 `meaning`은 DB 컬럼이 아니라 코드의 feature mapping table에서 붙인다.
