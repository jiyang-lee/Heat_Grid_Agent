# Retrieval Evaluation Dataset Guide

## 1. 데이터셋 목적

이 데이터셋은 HeatGrid RAG의 Retrieval 성능을 정량 평가하기 위한 질문-근거 라벨 초안이다. 목표 지표는 Recall@K, Precision@K, MRR, nDCG@K이며, 답변 생성 품질 평가는 이 단계의 범위가 아니다.

현재 RAG는 OpenAI semantic embedding 기반이 아니라 `hash_embedding` 기반 pgvector 검색과 JSONL lexical fallback 구조를 사용한다. 따라서 평가는 최신 semantic RAG와 비교 비판하기보다 운영 단순성, 의존성 최소화, Fault Group 기반 문서 회수라는 설계 목적을 기준으로 한다.

## 2. 각 필드 설명

| 필드 | 설명 |
|---|---|
| `case_id` | 평가 case의 고유 ID. `retrieval_eval_001` 형식을 사용한다. |
| `category` | 질문의 업무 범주. 운영 기준, 점검 행동, 고장 원인, 우선순위, 안전, 유사 사례, 답변 불가로 구분한다. |
| `query` | 실제 운영자가 물을 법한 검색 질문. 한국어와 영문 용어가 섞일 수 있다. |
| `query_intent` | 질문의 의도. 지표 분석 시 질문 성격별 성능을 나누는 축이다. |
| `query_type` | lexical exact match, paraphrase, multi-condition, ambiguous, unanswerable 여부를 나타낸다. |
| `difficulty` | 사람이 기대하는 검색 난도. 쉬움/중간/어려움으로 구분한다. |
| `fault_group` | HeatGrid 운영 관점의 고장군 또는 평가용 topic slug. |
| `substation_context` | 검색 질문의 설비/증상/제약 조건. 현재는 정적 평가용 설명이며 실행 입력이 아니다. |
| `expected_answer_points` | 관련 chunk가 회수되면 답변에 포함될 수 있는 문서 근거 포인트. |
| `forbidden_claims` | 답변 생성 평가 단계에서 금지해야 할 날조 유형. Retrieval 라벨 검수에도 참고한다. |
| `relevant_document_ids` | 질문에 직접 답하는 문서 제목 후보. |
| `relevant_chunk_ids` | 질문에 직접 답하는 gold chunk 후보. 반드시 `rag_chunks.jsonl`에 존재해야 한다. |
| `partially_relevant_chunk_ids` | 일부 맥락은 제공하지만 직접 정답으로 보기 어려운 chunk 후보. |
| `irrelevant_but_confusable_chunk_ids` | 키워드는 비슷하지만 정답으로 보면 안 되는 hard negative 후보. |
| `source_sections` | relevant chunk의 문서명, section, 사람이 검수할 근거 메모. |
| `answerable` | 정적 RAG 코퍼스로 답할 수 있는 질문인지 여부. |
| `review_required` | 사람이 라벨을 확인해야 하는지 여부. 초안은 모두 `true`로 시작한다. |
| `reviewer_notes` | 검수자가 먼저 확인할 점. 실행 확인 필요 시 `execution_validation_required`를 기록한다. |
| `label_status` | `draft`, `reviewed`, `approved` 중 하나. 자동 평가에는 `approved`만 쓰는 것을 권장한다. |
| `tags` | topic, source, risk 등을 자유롭게 분류하는 보조 태그. |

## 3. Relevant Chunk 선정 기준

Relevant chunk는 질문에 직접 답하는 핵심 문장을 포함해야 한다. 예를 들어 "온수가 늦게 나온다"는 질문에 대해 순환펌프 고장, 전원 공급, 펌프 하우징 공기 확인을 직접 말하는 Danfoss troubleshooting row는 relevant가 될 수 있다.

Relevant 여부는 검색 결과 rank가 아니라 문서 내용 기준으로 판단한다. `test_query_results.md`의 rank는 후보 발굴에만 사용하고 정답 라벨로 자동 승격하지 않는다.

## 4. Partially Relevant Chunk 기준

Partially relevant chunk는 질문의 배경, 인접 기준, 같은 증상군의 다른 원인을 설명하지만 질문에 직접 답하지 않는 chunk다. 예를 들어 strainer mesh 기준 질문에서 제조사 troubleshooting의 strainer 막힘 row는 배경은 되지만 mesh 규격의 직접 근거는 아니므로 partial 또는 confusable로 분류한다.

## 5. Unanswerable 질문 작성 기준

`answerable=false` 질문은 정적 코퍼스만으로 답하면 안 되는 질문이다. 예시는 미래 계측값, 현재 현장 적합/부적합 판정, 특정 기계실의 실제 공정일, 실시간 날씨 기반 설계 계산 등이다.

Unanswerable case에서는 `relevant_chunk_ids`를 비워 둔다. 기준 설명에 도움이 되는 문서가 있으면 `partially_relevant_chunk_ids`에 넣고, 답변이 값을 날조하지 않아야 한다는 점을 `forbidden_claims`에 명확히 기록한다.

## 6. Easy / Medium / Hard 기준

| 난도 | 기준 |
|---|---|
| `easy` | 질문 키워드와 문서 표현이 거의 일치하고 관련 chunk가 하나로 좁혀진다. |
| `medium` | 한국어 질문과 영문 문서 표현이 paraphrase 관계이거나, 같은 증상군의 여러 원인을 구분해야 한다. |
| `hard` | 다중 조건, 다중 문서 비교, 국제 기준 간 차이, 답변 불가와 부분 근거를 구분해야 한다. |

## 7. 사람 검수가 필요한 이유

PDF extraction 과정에서 표와 section title이 깨질 수 있고, 일부 chunk는 여러 주제가 한 행에 섞여 있다. 또한 hash embedding/lexical fallback 구조는 keyword overlap에 민감하므로, 자동 검색 결과가 relevance label을 대체할 수 없다.

초안의 모든 row는 `review_required=true`, `label_status=draft`다. 검수자는 실제 curated markdown 또는 원문 PDF 기준으로 relevant, partial, hard negative를 조정해야 한다.

## 8. Label 승인 절차

1. `relevant_chunk_ids`가 `rag_chunks.jsonl`에 실제 존재하는지 확인한다.
2. 각 relevant chunk가 질문에 직접 답하는지 원문 또는 curated text로 확인한다.
3. partial과 confusable을 서로 바꾸어야 하는 case가 있는지 검토한다.
4. expected answer points가 문서 근거를 벗어나지 않는지 확인한다.
5. 검수 완료 시 `label_status=reviewed`로 바꾸고, 실험에 투입할 수 있으면 `approved`로 승격한다.

## 9. 지표와 데이터셋 연결 방식

| 지표 | 사용하는 필드 | 계산 방식 |
|---|---|---|
| Recall@K | `relevant_chunk_ids`, 검색 결과 top K chunk IDs | gold relevant 중 top K에 포함된 비율 |
| Precision@K | `relevant_chunk_ids`, 검색 결과 top K chunk IDs | top K 중 gold relevant가 차지하는 비율 |
| MRR | `relevant_chunk_ids`, 검색 결과 rank | 첫 relevant chunk rank의 역수 |
| nDCG@K | `relevant_chunk_ids`, `partially_relevant_chunk_ids`, 선택적 graded label | relevant=2, partial=1, 그 외=0 같은 gain으로 DCG를 정규화 |

`irrelevant_but_confusable_chunk_ids`는 기본 ranking 지표 계산에는 직접 쓰지 않아도 되지만, hard negative hit rate 또는 오류 분석에 유용하다.

## 10. ops_retrieval_hits 활용 가능 범위

정적 코드 기준으로 `ops_retrieval_hits`는 어떤 chunk가 어떤 rank와 score로 검색되었는지 기록할 수 있는 구조다. 하지만 그 chunk가 질문에 실제로 relevant한지는 저장하지 않는다. 따라서 `ops_retrieval_hits`만으로 `relevant_chunk_ids`를 자동 복원할 수 없다.

또한 최신 `/api/agent-runs` 경로에서 `ops_retrieval_hits`가 항상 채워지는지는 실행 검증이 필요하다. 이 데이터셋에서는 관련 실행 확인이 필요한 경우 `reviewer_notes`에 `execution_validation_required`를 남긴다.
