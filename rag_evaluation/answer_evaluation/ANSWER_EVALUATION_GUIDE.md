# Answer Evaluation Guide

## 목적

이 문서는 HeatGrid RAG가 검색된 근거를 바탕으로 생성한 답변의 품질을 평가하기 위한 Draft/Reference 기준서다. 현재 단계에서는 실제 LLM 답변을 생성하지 않았으며, `answer_eval.draft.jsonl`의 `generated_answer`는 모두 `null`이다.

## 평가 대상

- Retrieval backend: JSONL lexical fallback
- Dataset status: `draft`
- Result level: `reference`
- Official benchmark: `false`

## 평가 항목

| 항목 | 설명 | 자동 평가 가능성 |
|---|---|---|
| Faithfulness | 답변의 주장이 retrieved context에서 뒷받침되는가 | LLM Judge 또는 사람 검수 필요 |
| Grounding Coverage | expected answer point가 검색 근거와 답변에 반영됐는가 | 일부 자동 가능 |
| Answer Relevance | 질문에 직접 답하고 불필요한 내용을 줄였는가 | LLM Judge 또는 사람 검수 필요 |
| Hallucination | 근거 없는 주장, 수치, 현장 결과를 생성했는가 | 규칙 + LLM Judge + 사람 검수 |
| Citation Accuracy | cited chunk가 실제 주장과 일치하는가 | 일부 자동, 최종은 사람 검수 |
| Citation Completeness | 근거가 필요한 핵심 주장에 citation이 붙었는가 | 일부 자동 |
| Unanswerable Handling | 답변 불가 질문에서 유보/추가자료 요청을 했는가 | 일부 자동 |
| Safety/Operational Caution | 고장 단정, 현장 결과 날조, 위험한 조치를 피했는가 | 사람 검수 필요 |

## 평가 그룹

Answer 평가 결과는 다음 그룹으로 반드시 분리 집계한다.

- Retrieval Hit: `retrieval_hit_at_5=true`
- Retrieval Miss: `retrieval_hit_at_5=false`
- `query_type=keyword_match`
- `query_type=semantic_paraphrase`
- `answerable=true`
- `answerable=false`

이 그룹은 검색 성공 여부와 질문 유형이 답변 품질에 미치는 영향을 분리해 보기 위한 것이다.

## 점수 정규화

자동 점수는 0~1 범위를 권장한다.

- `1.0`: 기준 완전 충족
- `0.5`: 부분 충족
- `0.0`: 미충족

사람 검수에서 0~2 척도를 쓰는 경우 `score / 2`로 0~1에 변환한다. 1~5 척도를 쓰는 경우 `(score - 1) / 4`로 변환한다.

## Draft/Reference 주의

현재 retrieval label과 answer evaluation dataset은 모두 draft 상태다. 따라서 이 단계에서 계산되는 answer score는 official benchmark가 아니라 기준 검증용 reference score다.
