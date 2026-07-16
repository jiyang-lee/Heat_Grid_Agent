# HeatGrid RAG Evaluation Report

## Executive Summary

HeatGrid RAG Evaluation은 Retrieval Evaluation, Answer Generation, Automatic Evaluation, LLM Judge, Manual Review까지 이어지는 end-to-end 평가 파이프라인으로 구성되었다. 전체 평가 대상은 28 cases이며, Retrieval 정량 평가는 answerable 25 cases를 기준으로 수행되었다. 현재 결과는 `draft` / `reference` 수준이며 `official_benchmark=false`로 관리된다.

Retrieval Evaluation 결과, Recall@5는 0.4, MRR은 0.32333333333333336으로 측정되었다. 이는 answerable case 중 40%에서 gold relevant chunk가 Top-5 안에 포함되었음을 의미한다. Retrieval Hit 그룹에서는 답변 생성 품질이 상대적으로 안정적이었으나, Retrieval Miss 그룹에서는 운영 유용성과 citation 평가에서 한계가 확인되었다.

LLM Judge 기준 주요 평균은 Faithfulness 3.607142857142857, Operational Usefulness 3.2857142857142856, Citation Accuracy Semantic 3.2857142857142856, Answer Relevance 4.035714285714286이다. Overall Recommendation 분포는 PASS 16, REVISE 10, FAIL 2로 나타났다. Retrieval Hit에서는 PASS 비율이 높았고, Retrieval Miss에서는 REVISE와 FAIL이 집중되었다.

Manual Review 결과, Judge 판정을 유지할 수 있는 case와 재검토가 필요한 case가 분리되었다. 특히 Retrieval Miss에서 안전한 유보 정책은 근거 없는 확정 답변 억제에는 효과적이었지만, Faithfulness와 Citation Accuracy 기준의 calibration 문제가 확인되었다. 이 파이프라인은 향후 Retrieval 구조, Prompt, Generation 모델, RAG 정책 변경 이후에도 동일 기준으로 성능 변화를 비교할 수 있는 HeatGrid 프로젝트의 기준 Evaluation Framework로 사용할 수 있다.

### Evaluation at a Glance

| 구분 | 핵심 결과 |
|---|---|
| Dataset | 28 cases |
| Retrieval | Recall@5 = 0.4, MRR = 0.32333333333333336 |
| Answer Generation | 28/28 success |
| Automatic Evaluation | citation_valid_ratio = 1.0, retrieval_miss_policy_pass_ratio = 1.0 |
| LLM Judge | Faithfulness, Operational Usefulness, Citation Accuracy Semantic, Answer Relevance 평가 |
| Recommendation | PASS 16 / REVISE 10 / FAIL 2 |
| Manual Review | 유지 가능 9 cases / 재검토 권장 6 cases |
| Benchmark Status | draft / reference / official_benchmark=false |

## 1. Evaluation Objective

HeatGrid RAG Evaluation의 목적은 HeatGrid 프로젝트의 RAG 구현이 운영자가 참고할 수 있는 근거 기반 답변을 생성하는지 정량적, 정성적으로 확인하는 것이다. 본 평가는 Retrieval만 별도로 측정하지 않고, 검색 결과가 실제 답변 생성과 품질 판단까지 어떻게 이어지는지 전체 파이프라인 관점에서 검토했다.

Retrieval 평가는 "정답 Chunk를 검색했는가"를 확인하지만, 실제 운영 품질은 다음 질문까지 포함해야 한다.

- 검색된 context가 답변에 적절히 사용되었는가
- 검색 실패 시 모델이 근거 없는 답변을 생성하지 않았는가
- citation이 실제 주장과 의미적으로 연결되는가
- 운영자가 다음 점검 행동을 판단하는 데 충분히 안전하고 유용한가

HeatGrid는 설비 운영, 고장 원인, 점검 기준, 안전 관련 문서를 다루므로 RAG 품질 평가는 단순 정확도보다 근거성, 환각 억제, 유보 표현, citation 직접성이 중요하다.

## 2. Evaluation Pipeline

```text
Evaluation Dataset
        |
        v
Retrieval Evaluation
        |
        v
Answer Generation
        |
        v
Rule-based Automatic Evaluation
        |
        v
LLM Judge
        |
        v
Manual Review
        |
        v
Final Evaluation Report
```

| 단계 | 역할 | 주요 산출물 |
|---|---|---|
| Evaluation Dataset | 질문, gold relevant chunk, expected answer points, forbidden claims 정의 | `answer_eval.draft.jsonl`, `retrieval_eval.review.jsonl` |
| Retrieval Evaluation | 검색 결과가 gold chunk를 포함하는지 측정 | `real_retrieval_results.jsonl`, `real_retrieval_summary.json` |
| Answer Generation | 검색 context만 사용해 답변 생성 | `answer_generation_all.jsonl`, `answer_generation_all_summary.json` |
| Automatic Evaluation | 규칙 기반으로 자동 확인 가능한 항목 검사 | `automatic_answer_eval_results.jsonl`, `automatic_answer_eval_summary.json` |
| LLM Judge | 의미 기반 답변 품질 평가 | `llm_judge_results.jsonl`, `llm_judge_summary.json` |
| Manual Review | Judge 결과의 타당성과 내부 일관성 검토 | `LLM_JUDGE_MANUAL_REVIEW.md` |

## 3. Evaluation Dataset

| 항목 | 값 |
|---|---:|
| 전체 case 수 | 28 |
| Retrieval 평가 대상 answerable case | 25 |
| Retrieval 평가 제외 unanswerable case | 3 |
| Answer Generation 대상 case | 28 |
| LLM Judge 대상 case | 28 |
| dataset_status | `draft` |
| result_level | `reference` |
| official_benchmark | `false` |

데이터셋은 질문별 gold relevant chunk를 기준으로 Retrieval 성능을 평가하도록 설계되었다. Answer Evaluation 단계에서는 `expected_answer_points`와 `forbidden_claims`를 사용해 답변이 기대 핵심을 포함하는지, 금지 주장을 생성하지 않는지 확인했다.

평가 데이터셋의 특징은 다음과 같다.

- answerable case와 unanswerable case를 모두 포함한다.
- Retrieval Hit와 Retrieval Miss가 모두 포함되어 있다.
- 고장 원인, 점검 조치, 운영 기준, 우선순위 설명, 안전 관련 질문을 포함한다.
- 현재 결과는 draft/reference 수준이며 공식 benchmark로 확정된 상태는 아니다.

## 4. Retrieval Evaluation

Retrieval Evaluation은 JSONL fallback backend를 기준으로 수행되었다. 전체 28 cases 중 answerable 25 cases가 정량 Retrieval metric 계산에 사용되었고, unanswerable 3 cases는 Retrieval metric 평균에서 제외되었다.

| 항목 | 값 |
|---|---:|
| 전체 case 수 | 28 |
| 평가 case 수 | 25 |
| 제외 unanswerable case 수 | 3 |
| 사용 backend | `jsonl` |
| failed case 수 | 0 |
| warning case 수 | 0 |
| 평균 retrieval latency ms | 16.78571428471644 |
| p50 retrieval latency ms | 15.999999828636646 |
| p95 retrieval latency ms | 31.00000019185245 |

| Metric | 값 |
|---|---:|
| Recall@1 | 0.28 |
| Recall@3 | 0.36 |
| Recall@5 | 0.4 |
| Precision@1 | 0.28 |
| Precision@3 | 0.12 |
| Precision@5 | 0.08 |
| HitRate@1 | 0.28 |
| HitRate@3 | 0.36 |
| HitRate@5 | 0.4 |
| MRR | 0.32333333333333336 |
| nDCG@5 | 0.29054645946376806 |

측정 방식과 해석은 다음과 같다.

- Recall@K는 gold relevant chunk 중 Top-K 검색 결과에 포함된 비율을 계산한다.
- Recall@5 = 0.4는 answerable case 중 40%에서 gold relevant chunk가 Top-5 안에 포함되었음을 의미한다.
- Precision@K가 낮은 이유는 Top-K 결과 중 실제 relevant chunk 비율을 계산하기 때문이다. Top-5 검색 결과에 정답 chunk가 1개 포함되더라도 나머지 결과가 relevant가 아니면 Precision@5는 낮아진다.
- MRR은 relevant chunk가 얼마나 높은 순위에 등장하는지를 보여준다. 값이 높을수록 첫 relevant chunk가 상위 rank에 등장한다.
- nDCG@5는 relevant와 partially relevant 결과의 순위 안정성을 함께 반영한다.
- 현재 Retrieval 수치만으로 운영 적용이 충분하다고 판단할 수는 없으며, semantic retrieval 개선 필요성을 보여준다.

주요 category별 해석은 다음과 같다.

- `similar_case` category는 Recall@5가 1.0으로 높았다.
- `priority_reason` category는 Recall@5가 0.0으로 낮았다.
- JSONL lexical fallback 구조는 명시적 키워드와 유사 troubleshooting row에는 강점이 있으나, 의미 재표현이나 연구/우선순위 문서 회수에는 한계가 확인되었다.

## 5. Answer Generation

Answer Generation은 Retrieval 결과를 입력 context로 사용해 전체 28 cases에 대해 수행되었다. 모델은 `gpt-5.4-mini`, prompt version은 `answer-generation-v1.1-miss-citation-strict`이다.

| 항목 | 값 |
|---|---:|
| 전체 case 수 | 28 |
| 생성 성공 case 수 | 28 |
| 실패 case 수 | 0 |
| warning case 수 | 8 |
| Retrieval Hit case 수 | 10 |
| Retrieval Miss case 수 | 15 |
| unanswerable case 수 | 3 |
| empty answer 수 | 0 |
| citation validation failure 수 | 0 |
| Retrieval Miss citation cleared 수 | 8 |
| answerable=false abstention 수 | 3 |
| model_name | `gpt-5.4-mini` |
| prompt_version | `answer-generation-v1.1-miss-citation-strict` |
| temperature | 0.0 |
| input tokens | 83358 |
| output tokens | 3727 |
| total tokens | 87085 |
| estimated_cost_usd | null |

Generation Prompt는 Retrieval Miss와 `answerable=false` 상황에서 무리한 citation 또는 확정 답변을 피하도록 설계되었다. 특히 Retrieval Miss에서 직접 근거가 없으면 `cited_chunk_ids=[]`를 허용하고, 추가 문서 또는 현장 확인 필요성을 명시하도록 했다.

## 6. Automatic Evaluation

Rule-based Automatic Evaluation은 LLM Judge 또는 사람 평가 전에 자동으로 확인 가능한 품질 조건을 점검하기 위한 단계다. 이 단계에서는 semantic faithfulness나 hallucination severity는 계산하지 않고, JSON 구조, citation 유효성, Retrieval Miss 정책 준수, forbidden claim 탐지 등 규칙 기반 항목만 계산했다.

| 항목 | 값 |
|---|---:|
| 전체 case 수 | 28 |
| coverage_average | 0.10714285714285714 |
| coverage_evaluated_count | 28 |
| citation_valid_ratio | 1.0 |
| forbidden_claim_detected_count | 0 |
| retrieval_miss_policy_pass_ratio | 1.0 |
| retrieval_miss_policy_evaluated_count | 15 |
| answerable_false_pass_ratio | 1.0 |
| answerable_false_evaluated_count | 3 |
| warning_total | 8 |
| error_total | 0 |
| json_valid_count | 28 |
| internal_label_leak_count | 0 |
| llm_judge_used | false |
| human_review_used | false |

Automatic Evaluation 결과는 안전 정책 준수 여부를 빠르게 확인하는 데 유용했다. 다만 `coverage_average`는 문자열 기반 규칙의 영향을 받으므로, 영어 expected point와 한국어 답변 사이의 의미적 일치를 충분히 반영하지 못한다. 따라서 최종 의미 품질 평가는 LLM Judge와 Manual Review에서 보완했다.

## 7. LLM Judge Results

LLM Judge는 Rule-based Evaluation으로 계산할 수 없는 의미 기반 품질 항목을 평가했다. Judge 입력에는 생성 답변, 검색 context, cited chunk, expected answer points, forbidden claims, answerable 여부, `retrieval_hit_at_5`만 포함했다.

| 항목 | 값 |
|---|---:|
| Judge Model | `gpt-5.4-mini` |
| Judge Prompt Version | `llm-judge-v1.0-draft` |
| Generation Model | `gpt-5.4-mini` |
| Judge와 Generation 동일 모델 여부 | true |
| 평가 case 수 | 28 |
| 실패 case 수 | 0 |
| API 호출 수 | 28 |
| retry_count | 0 |
| schema_validation_error_count | 0 |
| raw_response_issue_count | 0 |
| Faithfulness 평균 | 3.607142857142857 |
| Operational Usefulness 평균 | 3.2857142857142856 |
| Citation Accuracy Semantic 평균 | 3.2857142857142856 |
| Answer Relevance 평균 | 4.035714285714286 |
| total input tokens | 119258 |
| total output tokens | 6039 |
| total tokens | 125297 |
| estimated_total_cost_usd | null |
| recommendation_criteria_status | `calibration_required` |

| Hallucination Severity | case 수 |
|---|---:|
| NONE | 16 |
| MINOR | 11 |
| MAJOR | 1 |

| Overall Recommendation | case 수 |
|---|---:|
| PASS | 16 |
| REVISE | 10 |
| FAIL | 2 |

| Judge Confidence | case 수 |
|---|---:|
| HIGH | 27 |
| MEDIUM | 1 |

| 기준 | case |
|---|---|
| 최고 점수 case | `retrieval_eval_001`, `retrieval_eval_021` |
| 최저 점수 case | `retrieval_eval_006`, `retrieval_eval_008` |

Retrieval Hit/Miss별 LLM Judge 결과는 다음과 같다.

| 그룹 | case 수 | Faithfulness 평균 | Operational 평균 | Citation 평균 | Answer Relevance 평균 | PASS | REVISE | FAIL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Retrieval Hit | 10 | 4.5 | 4.3 | 4.3 | 5.0 | 9 | 1 | 0 |
| Retrieval Miss | 15 | 2.7333333333333334 | 2.466666666666667 | 2.2666666666666666 | 3.2 | 4 | 9 | 2 |
| answerable=false | 3 | 5.0 | 4.0 | 5.0 | 5.0 | 3 | 0 | 0 |

Query type별 결과는 다음과 같다.

| query_type | case 수 | Faithfulness 평균 | Operational 평균 | Citation 평균 | Answer Relevance 평균 | PASS | REVISE | FAIL |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| keyword_match | 11 | 3.5454545454545454 | 3.3636363636363638 | 3.272727272727273 | 4.090909090909091 | 7 | 3 | 1 |
| semantic_paraphrase | 7 | 3.142857142857143 | 2.857142857142857 | 2.4285714285714284 | 4.0 | 2 | 5 | 0 |

## 8. Manual Review

Manual Review의 목적은 LLM Judge 결과의 의미적 타당성과 내부 일관성을 evidence 기준으로 재검토하는 것이다. 검토 대상은 LLM Judge summary의 manual review priority case와 최고 점수 기준 case를 포함했다.

검토 대상 선정 기준:

- 낮은 점수 또는 FAIL/REVISE case
- `MAJOR` hallucination case
- Citation Accuracy 또는 Faithfulness 판단이 의심되는 case
- 최고 점수 기준 case

유지 가능 case:

- `retrieval_eval_001`
- `retrieval_eval_002`
- `retrieval_eval_003`
- `retrieval_eval_005`
- `retrieval_eval_007`
- `retrieval_eval_011`
- `retrieval_eval_014`
- `retrieval_eval_019`
- `retrieval_eval_021`

재검토 권장 case:

- `retrieval_eval_006`
- `retrieval_eval_008`
- `retrieval_eval_013`
- `retrieval_eval_015`
- `retrieval_eval_016`
- `retrieval_eval_024`

발견된 주요 이슈는 다음과 같다.

| 이슈 | 관련 case | 설명 |
|---|---|---|
| Retrieval Miss에서 Faithfulness/Citation 기준 일관성 부족 | `retrieval_eval_006`, `retrieval_eval_008`, `retrieval_eval_013`, `retrieval_eval_016` | 유사한 유보 답변에 대해 faithfulness/citation 고점과 저점이 혼재했다. |
| MAJOR Hallucination인데 REVISE 판정 | `retrieval_eval_024` | `hallucination_severity=MAJOR`이지만 final verdict는 `REVISE`로 남아 있어 보수적 재검토가 필요하다. |
| Citation critique 과도 가능성 | `retrieval_eval_015` | cited chunk가 gold/retrieved chunk와 일치하지만 citation score가 낮게 평가되었다. |
| 동일 모델 Judge confidence 과신 위험 | 다수 case | `HIGH` confidence가 27건으로 높지만 evidence 기준 재검토가 필요하다. |

Manual Review는 LLM Judge 결과를 직접 수정하지 않았으며, 별도 검토 의견으로만 기록했다.

## 9. Overall Analysis

### Key Findings

1. Retrieval 성능은 Answer Generation 품질에 직접적인 영향을 주었다. Retrieval Hit 그룹은 Retrieval Miss 그룹보다 주요 LLM Judge 지표에서 전반적으로 높았다.
2. Retrieval Hit 그룹은 Faithfulness 평균 4.5, Operational 평균 4.3, Citation 평균 4.3, Answer Relevance 평균 5.0으로 Retrieval Miss 그룹보다 높았다.
3. Retrieval Miss 유보 정책은 근거 없는 확정 답변 억제에는 효과적이었다. Answer Generation 결과에서 Retrieval Miss citation cleared 수는 8이고, Automatic Evaluation의 retrieval_miss_policy_pass_ratio는 1.0이다.
4. Retrieval Miss에서 Faithfulness와 Citation Accuracy 기준의 calibration 문제가 확인되었다. 유사한 유보 답변에 대해 Judge 점수가 일관되지 않은 case가 있었다.
5. Generation과 Judge에 동일 모델인 `gpt-5.4-mini`가 사용되어 자기평가 편향 가능성이 있다.
6. Manual Review는 Judge 결과의 불일치와 재검토 필요 case를 발견하는 데 필요했다.

### 장점

- 전체 평가 파이프라인이 Retrieval, Generation, Automatic Evaluation, LLM Judge, Manual Review까지 연결되어 있다.
- Retrieval 결과와 답변 품질을 분리해 분석할 수 있다.
- Retrieval Miss에서 citation을 비우고 유보 답변을 허용하는 정책이 구현되어 있다.
- Rule-based Evaluation이 JSON 형식, citation 유효성, forbidden claim, internal label leak 같은 기본 안전 조건을 자동 점검한다.
- LLM Judge와 Manual Review를 통해 단순 keyword coverage로 평가하기 어려운 의미 품질을 추가로 검토했다.

### 한계

- Retrieval backend가 JSONL lexical fallback 중심이므로 semantic paraphrase와 priority_reason 문서 회수에 약점이 확인되었다.
- Retrieval Miss case에서는 Generation 품질과 Retrieval 실패를 분리해서 해석해야 한다.
- LLM Judge와 Generation이 동일 모델이므로 자기평가 편향 가능성이 있다.
- 일부 한국어 원문 인코딩이 깨져 있어 사람이 세부 문장 품질을 검토하는 데 제약이 있다.
- 현재 결과는 draft/reference 수준이며 official benchmark가 아니다.

### 운영 적용 가능성

현재 결과는 운영 의사결정에 직접 사용하는 단계라기보다, 내부 검증 및 제한적 참고 수준으로 해석하는 것이 적절하다. Retrieval Hit 상황에서는 근거 기반 답변 품질이 상대적으로 안정적이었고, 특히 troubleshooting row처럼 구조화된 증상-원인-조치 표에서 strong evidence를 찾은 경우 LLM Judge 점수가 높았다.

다만 Retrieval Miss 상황에서는 답변이 안전하게 유보되더라도 운영 유용성이 낮아질 수 있다. 운영 의사결정에 직접 사용하려면 Retrieval 성능 개선, approved dataset 기반 재평가, Judge calibration, 도메인 전문가 검수, 운영 안전 기준 확정이 선행되어야 한다.

## 10. Limitations

본 평가의 한계는 다음과 같다.

- Generation과 Judge가 모두 `gpt-5.4-mini`이므로 동일 모델 편향 가능성이 있다.
- Retrieval Miss case는 "정답 미제공"과 "근거 없는 환각"을 분리하기 어렵다.
- Retrieval metric은 gold chunk label에 의존한다.
- 데이터셋은 draft 상태이며 approved benchmark가 아니다.
- Manual Review는 전체 28 cases 중 우선 검토 case와 최고 점수 case 중심으로 수행되었다.
- Automatic Evaluation의 coverage는 semantic matching이 아니라 rule-based matching이므로 실제 의미 포함률과 다를 수 있다.
- estimated cost는 공식 단가를 확정하지 못해 `null`로 유지되었다.

## 11. Future Work

향후 개선 작업은 다음 우선순위로 진행하는 것이 적절하다.

1. Retrieval 개선: semantic embedding, hybrid search, reranker, metadata filter를 도입해 `semantic_paraphrase`와 `priority_reason` 회수율을 높인다.
2. Dataset 승인: draft label을 reviewed/approved dataset으로 승격해 official benchmark 기반 평가를 수행한다.
3. Judge Calibration: Retrieval Miss 유보 답변에 대한 Faithfulness/Citation scoring 기준을 명확히 한다.
4. Cross-model Judge: 아직 수행하지 않은 단계이며, GPT-5.5 등 다른 계열 또는 상위 모델 Judge로 재평가해 동일 모델 편향을 줄인다.
5. Human Evaluation: 도메인 전문가가 Faithfulness, Operational Usefulness, Citation Accuracy를 직접 검수한다.
6. Multi Judge Voting: 여러 Judge 모델 또는 여러 prompt variant로 평가한 뒤 합의 기반 score를 구성한다.
7. RAGAS 비교: faithfulness, answer relevance 등 외부 RAG 평가 프레임워크와 결과를 비교한다.
8. Reporting 분리: Retrieval Failure, Generation Failure, Citation Failure, Judge Inconsistency를 최종 품질 리포트에서 분리 집계한다.

## 12. Conclusion

HeatGrid RAG Evaluation Pipeline은 Retrieval에서 최종 Manual Review까지 이어지는 end-to-end 평가 체계를 구축했다. Retrieval Evaluation은 JSONL fallback 검색의 강점과 한계를 정량적으로 보여주었고, Answer Generation은 Retrieval Miss와 unanswerable 상황에서 안전한 유보 정책을 검증했다.

Automatic Evaluation은 기본 형식과 정책 준수 여부를 안정적으로 점검했으며, LLM Judge는 Faithfulness, Hallucination, Operational Usefulness, Citation Accuracy, Answer Relevance를 의미적으로 평가했다. Manual Review는 LLM Judge 결과 중 일부 calibration 이슈와 동일 모델 편향 가능성을 식별했다.

현재 결과는 official benchmark가 아닌 draft/reference 평가 결과다. 그럼에도 본 파이프라인은 HeatGrid RAG 품질을 반복적으로 측정하고, Retrieval 개선과 Answer 품질 개선을 분리해 추적할 수 있는 기반을 제공한다. 또한 향후 Retrieval 구조, Prompt, Generation 모델, RAG 정책 변경 이후에도 동일한 기준으로 성능 변화를 비교할 수 있는 HeatGrid 프로젝트의 기준 Evaluation Framework로 사용할 수 있다.
