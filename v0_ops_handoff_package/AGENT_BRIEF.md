# Agent Brief

## 작업 배경

이 패키지는 v0 HeatGrid 운영보조 agent의 입력 및 출력 계약을 정의합니다.
현재 목표는 LangGraph ReAct 운영보조 agent의 최종 출력 JSON 형식을 고정하고, local curated RAG context가 최종 문장 생성에 들어가는지 검증하는 것입니다. embedding/vector search 서버는 범위에 포함하지 않습니다.

## Agent 흐름

```text
1. 화면에서 card_id를 선택합니다.
2. LangGraph agent를 시작합니다.
3. agent가 get_ops_evidence(card_id)를 호출합니다.
4. get_ops_evidence는 raw_context, priority_context, internal_context를 반환합니다.
5. agent는 필요할 경우 get_external_context(card_id)를 호출할 수 있습니다.
6. 현재 get_external_context는 `data/rag_sources/metadata/rag_chunks.jsonl`에서 관련 chunk를 검색해 external_context를 반환합니다.
7. LLM이 최종 JSON 출력을 생성합니다.
8. 출력 JSON은 contracts/ops_agent_output.schema.json으로 검증합니다.
9. 검증에 실패한 출력은 에러로 표시하고 저장하지 않습니다.
10. 검증에 성공한 출력만 화면에 표시하고 저장합니다.
```

## 입력 계약

기존 공개 agent 입력 구조는 유지합니다.

```text
raw_context
priority_context
internal_context        # optional DB-backed context
```

`priority_context`에는 risk, anomaly, leadtime 세부 필드를 추가하지 않습니다.
해당 세부 정보는 DB에 남기거나 향후 내부 전용 context에서 다룹니다.

사용하는 priority 경로:

```text
priority_context.priority.calculation
priority_context.explanation.review_required
priority_context.explanation.review_reasons
```

사용하지 않는 경로:

```text
priority_context.formula
priority_context.review_reasons
priority_context.card.review_required
```

## Internal Context

`internal_context`는 v0에서 optional입니다. 존재할 경우 아래 5개 묶음만 포함합니다.

```text
internal_context.data_quality
internal_context.model_provenance
internal_context.asset_context
internal_context.ops_history
internal_context.window_context
```

v0 `input.json`에는 `feature_meta`, `sensor_summaries`, `model_runs`, `model_outputs` 전체 목록을 넣지 않습니다.

운영용 기본 입력에는 정답 라벨처럼 보일 수 있는 검증용 필드를 넣지 않습니다.

```text
validation_labels
label
fault_label
fault_event_id
estimated_lead_time_hours
lead_time_bucket
```

평가 전용 데이터가 필요하면 기본 운영용 입력이 아니라 별도의 `evaluation_context`로 분리합니다.

## 출력 계약

최종 LLM 출력은 아래 top-level 구조를 가진 JSON이어야 합니다.

```text
decision
summary
action_plan
caution
evidence
```

매핑 규칙:

```text
decision.priority <- priority_context.priority.priority_level
decision.operator_review <- priority_context.explanation.review_required가 true이면 Required, false이면 Not Required
decision.data_quality <- internal_context.data_quality를 기준으로 Good, Medium, Low, Unknown 중 하나로 변환

evidence.priority_score <- priority_context.priority.priority_score
evidence.current_best <- priority_context.model_signals.current_best_priority_level
evidence.m1_specialist <- priority_context.model_signals.m1_specialist_fault_group, 없으면 m1_specialist_priority_level 사용
evidence.main_signals <- review reason, 주요 센서 값, M1 feature 근거에서 3~5개로 요약
evidence.used_tools <- 실제 실행 중 호출된 tool 이름
```

출력 제약:

```text
summary: 짧은 1~3문장
action_plan: 2~5개 항목
caution: 1~4개 항목
```

화면 표시 순서:

```text
Decision
Summary
Action Plan
Caution
Evidence
```

UI에서 지원한다면 Evidence는 접기/펼치기 영역으로 표시합니다.

## 기대값

```text
current_best_sensor_values_count = 10
m1_specialist_feature_count = 13
priority_score = 89.73322568799986
priority_level = urgent
current_best_weight = 0.65
m1_specialist_weight = 0.35
```

## 제외 범위

```text
embedding 서버
vector DB
prompt server
UI implementation
```

## 주요 파일

```text
input.json
examples/ops_agent_input.example.json
examples/ops_agent_output.example.json
contracts/ops_agent_input.schema.json
contracts/ops_agent_output.schema.json
db/schema.sql
db/seed.sql
queries/verify.sql
```
