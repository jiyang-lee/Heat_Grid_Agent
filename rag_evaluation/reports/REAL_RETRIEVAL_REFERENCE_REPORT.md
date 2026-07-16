# Real Retrieval Reference Report

## 1. ?? ??

? ???? 4??/4.5???? ??? Retrieval Evaluation Engine? ???? `RagSearcher` ?? ?? ??? ??? Draft/Reference ??? Retrieval metric? ??? ???. Generation, Grounding, Faithfulness, Hallucination, Citation Accuracy? ???? ???.

## 2. Dataset ??

- dataset_path: `C:\project3.3_develop\Heat_Grid_Agent\rag_evaluation\review\retrieval_eval.review.jsonl`
- dataset_status: `draft`
- result_level: `reference`
- official_benchmark: `False`
- ??: ?? dataset? `label_status=draft`, `review_required=true` ????? Official Benchmark? ???.

## 3. ?? ?? Backend

- requested_backend: `jsonl`
- backend_usage_counts: `{'jsonl': 28}`
- JSONL backend? ??/DB ?? ?? ????.
- pgvector backend? ?? ???? active backend? `pgvector`? ???? ?? skip??. ingest? DB ??? ??? ???? ???.

## 4. ?? ??? ??

- ???? `RagSearcher`? import?? ????.
- ?? RAG ??? ???? ???.
- ?? query? dataset? `query`? ??? ???? ?? ????? ???.
- `fault_group`, `category`, `query_intent`, `substation_context`? adapter metadata/evidence? ?? ??? ????? ????.
- ?? JSONL lexical scoring? ??? query? ?? chunk ? lexical mismatch? ??? ? ??.

## 5. ?? Metric

| metric | value |
|---|---:|
| `recall_at_1` | 0.2800 |
| `recall_at_3` | 0.3600 |
| `recall_at_5` | 0.4000 |
| `precision_at_1` | 0.2800 |
| `precision_at_3` | 0.1200 |
| `precision_at_5` | 0.0800 |
| `hit_rate_at_1` | 0.2800 |
| `hit_rate_at_3` | 0.3600 |
| `hit_rate_at_5` | 0.4000 |
| `mrr` | 0.3233 |
| `ndcg_at_5` | 0.2905 |

## 6. Category? ??

| group | case_count | evaluated | Recall@5 | HitRate@5 | MRR | nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| `fault_cause` | 2 | 2 | 0.5000 | 0.5000 | 0.5000 | 0.3194 |
| `inspection_action` | 7 | 7 | 0.2857 | 0.2857 | 0.2143 | 0.1771 |
| `operating_standard` | 8 | 8 | 0.3750 | 0.3750 | 0.2812 | 0.3504 |
| `priority_reason` | 3 | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| `safety_caution` | 3 | 3 | 0.6667 | 0.6667 | 0.4444 | 0.4347 |
| `similar_case` | 2 | 2 | 1.0000 | 1.0000 | 1.0000 | 0.6388 |
| `unanswerable` | 3 | 0 | n/a | n/a | n/a | n/a |

## 7. Difficulty? ??

| group | case_count | evaluated | Recall@5 | HitRate@5 | MRR | nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| `easy` | 8 | 6 | 0.3333 | 0.3333 | 0.2222 | 0.1698 |
| `hard` | 4 | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| `medium` | 16 | 16 | 0.5000 | 0.5000 | 0.4219 | 0.3903 |

## 8. Query Intent? ??

| group | case_count | evaluated | Recall@5 | HitRate@5 | MRR | nDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| `comparison` | 2 | 2 | 0.5000 | 0.5000 | 0.5000 | 0.4640 |
| `fault_cause` | 4 | 4 | 0.7500 | 0.7500 | 0.7500 | 0.4791 |
| `inspection_action` | 7 | 7 | 0.2857 | 0.2857 | 0.2143 | 0.1771 |
| `operating_standard` | 6 | 6 | 0.3333 | 0.3333 | 0.2083 | 0.3126 |
| `priority_reason` | 3 | 3 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| `safety` | 3 | 3 | 0.6667 | 0.6667 | 0.4444 | 0.4347 |
| `unknown` | 3 | 0 | n/a | n/a | n/a | n/a |

## 9. Retrieval Latency

| latency metric | ms |
|---|---:|
| average | 16.7857 |
| p50 | 16.0000 |
| p95 | 31.0000 |

Agent ?? ?? ???? LLM ??? ???? ???.

## 10. ?? ?? ? Warning

- failed_case_count: 0
- warning_case_count: 0
- excluded_unanswerable_count: 3
- evaluated_case_count: 25

## 11. ??? ?? Case Top ??

| case_id | query | Recall@5 | HitRate@5 | MRR | nDCG@5 | actual_backend | warnings |
|---|---|---:|---:|---:|---:|---|---|
| `retrieval_eval_002` | 온수가 늦게 나오면 순환펌프 쪽에서는 무엇을 점검해야 해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_003` | 급탕 온도가 낮고 변동이 있으면 욕실 믹서의 역류방지밸브도 의심 대상이야? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_005` | 시운전 전에 배관 연결부와 누수 확인은 어떤 순서로 해야 해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_006` | 안전밸브 배출관은 어디로 유도해야 하고 차단밸브를 넣어도 돼? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_007` | 국내 준공점검에서 1차측 열량계와 스트레이너는 어떤 설치 상태를 확인해야 해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_008` | 중간점검은 고객이 언제 신청해야 하고 미비하면 어떻게 처리돼? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_010` | PDCV 도압관은 공급측과 회수측을 어디에 연결하는 게 적정해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_011` | risk score가 높은 지점의 점검 우선순위를 설명할 때 FMEA 기반으로 어떤 근거를 들 수 있어? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_012` | strainer fault priority를 설명할 때 발생도, 심각도, 모니터링 가능성 같은 축을 같이 써야 해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_013` | control valve actuator travel time 설정 오류는 우선순위 연구에서 어느 정도 위험 사례로 언급돼? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |

## 12. Relevant Chunk? Top-5? ?? ???? ?? Case

| case_id | query | Recall@5 | HitRate@5 | MRR | nDCG@5 | actual_backend | warnings |
|---|---|---:|---:|---:|---:|---|---|
| `retrieval_eval_002` | 온수가 늦게 나오면 순환펌프 쪽에서는 무엇을 점검해야 해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_003` | 급탕 온도가 낮고 변동이 있으면 욕실 믹서의 역류방지밸브도 의심 대상이야? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_005` | 시운전 전에 배관 연결부와 누수 확인은 어떤 순서로 해야 해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_006` | 안전밸브 배출관은 어디로 유도해야 하고 차단밸브를 넣어도 돼? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_007` | 국내 준공점검에서 1차측 열량계와 스트레이너는 어떤 설치 상태를 확인해야 해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_008` | 중간점검은 고객이 언제 신청해야 하고 미비하면 어떻게 처리돼? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_010` | PDCV 도압관은 공급측과 회수측을 어디에 연결하는 게 적정해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_011` | risk score가 높은 지점의 점검 우선순위를 설명할 때 FMEA 기반으로 어떤 근거를 들 수 있어? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_012` | strainer fault priority를 설명할 때 발생도, 심각도, 모니터링 가능성 같은 축을 같이 써야 해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_013` | control valve actuator travel time 설정 오류는 우선순위 연구에서 어느 정도 위험 사례로 언급돼? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_014` | 지역난방 기계실 strainer mesh는 국제 기준에서 어느 정도로 잡고 압력계는 왜 양쪽에 달아? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_016` | brazed plate heat exchanger와 gasket type은 어떤 상황에서 다르게 선택해? | 0.0000 | 0.0000 | 0.0000 | 0.1677 | `jsonl` | - |
| `retrieval_eval_017` | 급탕제어기는 난방제어와 연계해서 과부하시 어떻게 동작해야 해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_019` | 준공점검 서식에서 난방순환펌프와 판형열교환기는 무엇을 확인해서 적어야 해? | 0.0000 | 0.0000 | 0.0000 | 0.0000 | `jsonl` | - |
| `retrieval_eval_024` | commissioning 때 난방과 급탕 밸런싱 후 어떤 기록과 기능점검이 필요해? | 0.0000 | 0.0000 | 0.0000 | 0.5209 | `jsonl` | - |

## 13. Top-1?? ??? Top-5?? ??? Case

| case_id | query | Recall@5 | HitRate@5 | MRR | nDCG@5 | actual_backend | warnings |
|---|---|---:|---:|---:|---:|---|---|
| `retrieval_eval_004` | DHW 온도가 tapping 중 떨어질 때 차압제어 capillary tube와 열교환기는 어떤 조치 후보가 있어? | 1.0000 | 1.0000 | 0.5000 | 0.4796 | `jsonl` | - |
| `retrieval_eval_015` | two-port control valve를 쓰는 이유와 self-acting/electric control valve 선택 기준을 설명할 근거가 있어? | 1.0000 | 1.0000 | 0.2500 | 0.5945 | `jsonl` | - |
| `retrieval_eval_020` | 기계실 인입 1차측 배관 용접 후면비드는 어떤 용접 방식이어야 해? | 1.0000 | 1.0000 | 0.3333 | 0.3801 | `jsonl` | - |

## 14. JSONL/pgvector ?? ?? ??

?? ????? JSONL ??? ????. pgvector? ?? ???? unavailable? ???? ?? ??? ???? ???. ??? ???? PostgreSQL/pgvector ???, `psycopg`, `rag_chunks` ?? ?? ??? ????.

## 15. ?? ?? ? ????

- ? ??? Draft/Reference metric?? ?? ?? ??? ???.
- review label? ?? ?? ?? ???.
- JSONL lexical fallback? query ??? ?? ??? ????.
- ?? ??? retrieval ?? ??? draft label ??? ??? ??? ? ??.
- ?? ??? ???? ???? ???.

## 16. Approved Dataset ?? ??? ??

1. `retrieval_eval.approved.jsonl`? ????.
2. ?? runner? JSONL backend? ?????.
3. pgvector ??? ??? ? `--backend pgvector`? ?? ??? ????.
4. backend/top_k? ?? ???? ?? ????.
