# LLM Judge Evaluation Guide

## 목적

LLM Judge는 Rule-based Automatic Evaluation에서 계산하지 못한 의미 기반 품질을 평가한다. 평가 대상은 `answer_generation_all.jsonl`의 28개 답변이며, 기존 결과와 병합하지 않고 별도 결과로 저장한다.

## Generation과 Judge 분리

Generation 단계에서는 `expected_answer_points`, `forbidden_claims`, `relevant_chunk_ids` 같은 평가 정답 정보를 사용하지 않았다. Judge 단계에서는 채점 목적으로 `expected_answer_points`와 `forbidden_claims`를 사용할 수 있다. 단, Judge 결과는 생성 결과를 수정하지 않는다.

## Judge 입력

- query
- generated_answer
- cited_chunk_ids
- retrieved_contexts
- expected_answer_points
- forbidden_claims
- answerable
- retrieval_hit_at_5

## 평가 항목

| 항목 | 범위 | 설명 |
|---|---|---|
| Faithfulness | 0~5 | 답변 핵심 주장이 retrieved context에 근거하는지 평가 |
| Hallucination Severity | NONE/MINOR/MAJOR/CRITICAL | 근거 없는 원인, 수치, 현장 결과, 위험 지시 여부 평가 |
| Operational Usefulness | 0~5 | 운영자가 실제로 사용할 수 있는 답변인지 평가 |
| Citation Accuracy Semantic | 0~5 | cited chunk가 답변 주장과 의미적으로 연결되는지 평가 |
| Answer Relevance | 0~5 | 질문의 핵심 의도에 직접 답했는지 평가 |
| Overall Recommendation | PASS/REVISE/FAIL | 평가 결과 사용 가능성에 대한 종합 권고 |
| Judge Confidence | HIGH/MEDIUM/LOW | Judge 판단의 확실성 |

## Citation Accuracy 보완 기준

`cited_chunk_ids=[]` 자체는 낮은 점수 사유가 아니다. Retrieval Miss 또는 `answerable=false`에서 직접 근거가 없어 안전하게 유보한 경우, 빈 citation은 적절한 처리이며 5점도 가능하다.

감점은 다음 경우에 적용한다.

- 근거가 필요한 핵심 주장을 했는데 citation이 없다.
- citation이 주제만 비슷하고 핵심 주장을 직접 뒷받침하지 않는다.
- retrieved context 밖 ID 또는 문서 ID를 citation처럼 사용한다.

## Answer Relevance 기준

| 점수 | 기준 |
|---:|---|
| 5 | 질문의 핵심 의도에 직접 답하고 불필요한 내용이 거의 없다. |
| 4 | 질문에 잘 답하지만 일부 보조 설명이 길거나 초점이 약간 넓다. |
| 3 | 질문과 관련 있고 부분적으로 답하지만 핵심 의도 일부가 부족하다. |
| 2 | 관련 정보는 있으나 질문의 핵심 답변이 약하거나 간접적이다. |
| 1 | 주제는 비슷하지만 질문에 거의 답하지 못한다. |
| 0 | 질문과 무관하거나 반대로 답한다. |

## Overall Recommendation 임시 기준

기준 상태는 `calibration_required`다.

| 값 | 임시 기준 |
|---|---|
| PASS | `faithfulness >= 4`, `citation_accuracy_semantic >= 4`, `answer_relevance >= 3`, MAJOR/CRITICAL 없음 |
| REVISE | 수정 가능한 근거, 인용, 표현 문제가 있으나 핵심 방향은 유효함 |
| FAIL | `faithfulness <= 1`, CRITICAL, 또는 운영상 위험한 MAJOR |

## Judge Confidence 기준

| 값 | 기준 |
|---|---|
| HIGH | 근거와 답변 연결이 명확하고 채점 판단이 안정적이다. |
| MEDIUM | 대체로 판단 가능하지만 일부 citation 직접성 또는 도메인 해석이 애매하다. |
| LOW | 도메인 판단이 필요하거나 근거 연결이 불명확하다. |

## 주의사항

- LLM Judge는 최종 진실이 아니라 의미 평가 보조자다.
- Official Benchmark로 사용하려면 사람 검수 또는 도메인 전문가 검토가 필요하다.
- Judge가 답변을 수정하거나 새 답변을 생성해서는 안 된다.
- Citation ID 유효성은 이미 Rule-based 단계에서 확인했으므로, Judge는 의미적 연결성을 본다.

## 2단계 실행 전 확인

- 예상 호출 수: 28
- 사용할 Judge Model
- Judge Prompt Version: `llm-judge-v1.0-draft`
- 예상 입력/출력 토큰
- 예상 비용 또는 비용 산정 불가 사유
- 기존 결과 JSONL 해시 보존 여부
