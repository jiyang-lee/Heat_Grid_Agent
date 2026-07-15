# Evaluation Readiness

평가 기준: 최신 로컬 `develop2` 커밋 `bb3fb32`의 RAG 구현을 대상으로 한다. 서버, DB, Docker는 실행하지 않았으므로 runtime 상태와 실제 수치는 실행 검증 필요로 둔다.

## 평가 항목 준비 상태

| 평가 항목 | 준비 상태 | 현재 활용 가능한 데이터 | 부족한 데이터 | 필요한 최소 추가 작업 | 우선순위 |
|---|---|---|---|---|---|
| Recall@K | 추가 구현 필요 | `rag_chunks.jsonl`, 검색 결과 `chunks`, `RagEvidenceSnapshot` 구조 | 질문별 relevant chunk/document label | 평가 JSONL에 `query`, `relevant_chunk_ids` 추가 | 높음 |
| Precision@K | 추가 구현 필요 | rank가 있는 검색 결과, `ops_retrieval_hits` 저장 구조 | retrieved chunk의 relevance label | human label 또는 검수된 LLM judge label 구축 | 높음 |
| MRR | 추가 구현 필요 | 검색 결과 순위 | 첫 relevant result 판정 label | query별 relevant chunk set 구축 | 높음 |
| nDCG@K | 추가 구현 필요 | rank와 score 구조 | graded relevance label | 0/1/2 등급 relevance annotation | 중간 |
| Grounding | 일부 가능 | retrieval chunks, `source_input`, agent output, `agent_runs.ops_output` | 답변 문장과 근거 chunk alignment | 답변과 검색 context를 같은 case log로 저장 | 높음 |
| Faithfulness | 일부 가능 | source input, retrieval context, final answer 구조 | claim 단위 근거 판정 label | claim rubric 또는 수동 평가 sheet 구성 | 높음 |
| Answer Relevance | 일부 가능 | priority card/source input/final answer | case별 expected answer points | 평가 JSONL에 기대 조치/주의사항 label 추가 | 높음 |
| Hallucination | 일부 가능 | final answer, source input, retrieval context | forbidden/unsupported claim 기준 | 수동 평가 또는 LLM judge + spot check | 높음 |
| Citation Accuracy | 추가 구현 필요 | `references.technical_standards`, chunk metadata | 답변 문장과 citation 연결 | citation id 출력 또는 사후 alignment label 추가 | 중간 |
| Retrieval Latency | 추가 구현 필요 | 검색 함수/adapter 경로 | 검색 시작/종료 timestamp | RAG adapter/search wrapper 계측 | 높음 |
| End-to-End Latency | 일부 가능 | agent task/run 실행 구조, 일부 latency/token 필드 | route/task 시작/종료 기준의 일관된 timestamp | 실제 run log 확인 및 필요 시 timestamp 수집 | 중간 |
| Token Usage | 일부 가능 | `TokenUsage`, `TokenCall`, diagnostic token budget, `agent_runs.token_usage` | with/without RAG별 case 연결 | run별 token usage와 case id 매핑 | 중간 |
| with_rag / no_rag 비교 | 일부 가능 | `src/heatgrid_rag/server.py` compare convention, agent runtime port 구조 | 동일 input의 답변 쌍 | 고정 case set과 동일 조건 실행 결과 수집 | 높음 |
| pgvector / JSONL fallback 비교 | 일부 가능 | `HEATGRID_RAG_BACKEND`, `RagSearcher`, `InternalRagEvidenceAdapter` | 동일 query에서 두 backend 결과 | backend 강제 실행 후 결과 JSONL 저장 | 높음 |
| top_k 비교 | 일부 가능 | `top_k` parameter, 1~20 clamp, evidence loop top_k 확장 | top_k별 retrieval/answer 결과 | top_k grid 실험 결과 저장 | 중간 |
| embedding 방식 비교 | 추가 구현 필요 | 현재 `hash_embedding`, pgvector schema | 비교 embedding index/fixture | semantic embedding 후보를 별도 index로 만들고 동일 query 비교 | 낮음 |

## 추가 분석

### 1. Recall@K, Precision@K, MRR에 필요한 label

필요하다. `ops_retrieval_hits`와 retrieval result는 어떤 chunk가 나왔는지는 알려주지만, 그 chunk가 질문에 relevant한지는 알려주지 않는다. 최소 dataset은 `query`, `fault_group`, `relevant_chunk_ids`, `relevant_document_ids`를 가져야 한다.

### 2. Grounding 및 Faithfulness에 필요한 저장 데이터

검색 context와 최종 답변을 함께 저장해야 한다. 최신 구조에서는 `AgentRuntime.external_context_for()`가 만든 `retrieval/site/weather` context와 final `OpsAgentOutput`을 같은 case id로 묶는 것이 핵심이다. diagnostic worker가 개입한 경우 `diagnostic_summary`와 선택된 RAG evidence id도 함께 저장해야 한다.

### 3. Latency 평가에 필요한 timestamp

Retrieval Latency는 RAG adapter/search 시작/종료 timestamp가 필요하다. End-to-End Latency는 agent run 또는 task 단위 시작/종료 timestamp가 필요하다. 현재 정적 코드상 retrieval 전용 timestamp 필드는 확인되지 않았다.

### 4. Hallucination 평가 자동화 가능성

완전 자동화는 어렵다. 운영 도메인에서는 수동 평가 또는 LLM Judge + human spot check가 적절하다. 자동화 보조로는 source/retrieval에 없는 원인 단정, 수치, 고유명사, 날씨 원인화 같은 forbidden claim 탐지가 가능하다.

### 5. 현재 ops_retrieval_hits와 Agent 로그만으로 가능한 평가

가능한 것:

- run별 검색 chunk 목록, rank, score, role/fault type 분포
- 검색 chunk 편향과 반복 회수 분석
- token usage 분석, 단 case id와 run id 연결 필요
- diagnostic worker fallback/trigger 분석, 단 최신 run log 확인 필요

어려운 것:

- Recall@K, Precision@K, MRR, nDCG@K
- 답변 grounding/faithfulness 자동 판정
- citation accuracy
- retrieval latency 단독 측정

주의: `ops_retrieval_hits`는 코드상 존재하지만 최신 `/api/agent-runs` 실행에서 항상 기록되는지는 실행 검증 필요다.

## 권장 평가 데이터셋 JSONL 구조

```json
{
  "case_id": "case-001",
  "query": "district heating strainer differential pressure leakage",
  "source_input_ref": {
    "card_id": "redacted-or-synthetic",
    "alert_id": "redacted-or-synthetic"
  },
  "fault_group": "leakage_water_loss",
  "priority_level": "high",
  "relevant_chunk_ids": ["danfoss_troubleshooting_table__row001"],
  "relevant_document_ids": ["doc-id-or-title"],
  "graded_relevance": {
    "danfoss_troubleshooting_table__row001": 2
  },
  "expected_answer_points": [
    "check strainer differential pressure",
    "verify flow meter readings"
  ],
  "forbidden_claims": [
    "weather caused the fault"
  ],
  "citation_expectations": [
    {
      "answer_point": "check strainer differential pressure",
      "supporting_chunk_ids": ["danfoss_troubleshooting_table__row001"]
    }
  ],
  "diagnostic_expected": false,
  "split": "dev",
  "label_source": "human"
}
```

## 우선 수행 순서

1. Retrieval label dataset을 먼저 만든다. `relevant_chunk_ids`가 있어야 핵심 ranking 지표가 계산된다.
2. 동일 query set으로 pgvector와 JSONL fallback 결과를 수집한다.
3. with_rag/no_rag 답변 쌍을 만들고 `retrieval_context + final_answer + source_input + token_usage + diagnostic_summary`를 함께 저장한다.
4. latency 계측은 검색 품질 평가와 분리해 별도 instrumentation 작업으로 잡는다.

