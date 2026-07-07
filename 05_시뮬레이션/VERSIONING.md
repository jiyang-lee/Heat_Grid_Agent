# Simulation Versioning

`05_시뮬레이션`은 실험 버전을 폴더 단위로 관리한다.

## Rule

한 버전은 다음 3가지를 함께 가진다.

1. input/output JSON 계약
2. 예시 input/output JSON
3. 해당 버전의 실행 결과

## Folder Pattern

```text
05_시뮬레이션/
  versions/
    v0_minimal_ops/
      README.md
      contracts/
      examples/
      outputs/
```

## Current Versions

| version | purpose | status |
|---|---|---|
| `v0_minimal_ops` | DB 기반 최소 ops-agent 시뮬레이션 | active |
| `v1_langgraph_react_ops` | LangGraph ReAct Agent 기반 ops-agent 시뮬레이션 | active |

## Planned Versions

| version | added context |
|---|---|
| `v2_weather_context` | weather API 결과 |
| `v3_rag_context` | 운영 문서 RAG 결과 |
| `v4_weather_rag_ops` | weather + RAG 통합 |

## Naming Rule

새 기능이 들어가면 기존 버전을 수정하지 않고 새 버전을 만든다.

```text
v0_minimal_ops
v1_langgraph_react_ops
v2_weather_context
v3_rag_context
v4_weather_rag_ops
```

기존 실험의 계약과 결과를 보존해야 나중에 "어떤 입력으로 어떤 답이 나왔는지"를 되짚을 수 있다.
