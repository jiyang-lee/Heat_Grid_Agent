# Auto vs Human Evaluation Plan

## 자동 계산 가능한 항목

- expected_answer_points의 문자열/키워드 포함률
- forbidden_claims 관련 금지 표현 탐지
- cited_chunk_ids 존재 여부
- cited_chunk_ids가 retrieved_chunk_ids 안에 있는지 여부
- answerable=false 질문에서 유보 표현이 있는지 규칙 검사
- citation completeness의 형식적 검사

## LLM Judge가 필요한 항목

- Faithfulness: 답변 주장이 context에 의해 의미적으로 뒷받침되는지
- Answer Relevance: 질문 의도에 맞게 답했는지
- 의미 기반 Hallucination: 원문에 없는 주장을 했는지
- Citation Accuracy: citation이 실제 주장을 뒷받침하는지

LLM Judge 결과는 최종 정답이 아니다. `automated_scores` 또는 별도 judge metadata에 저장하고, 사람 검수 결과와 분리해야 한다.

## 사람 검수가 필요한 항목

- 운영상 유용성
- 안전한 표현
- 원인 단정 여부
- 도메인 기준 해석
- 심각한 hallucination 판정
- Retrieval Miss에서 유보 태도가 충분한지

## 권장 저장 방식

- 규칙 기반 점수: `automated_scores`
- LLM Judge 점수: `automated_scores` 내부 또는 별도 judge metadata
- 사람 검수 점수: `human_scores`
- 최종 판단: `label_status`와 `review_required`

## 단계별 실행 계획

1. generated_answer와 cited_chunk_ids를 채운다.
2. 규칙 기반 자동 점수를 계산한다.
3. LLM Judge를 선택적으로 실행한다.
4. 도메인 사람이 high-risk case를 검수한다.
5. `reviewed` 또는 `approved`로 승격한다.
