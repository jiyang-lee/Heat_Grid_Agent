# Retrieval 평가 데이터셋 검수 가이드

이 문서는 `retrieval_eval_review.md`, `retrieval_eval_review.csv`, `retrieval_eval.review.jsonl`을 검수할 때 사용할 한국어 기준서다. JSON field name, enum 값, `case_id`, `chunk_id`, `candidate_type`, `label_status`, `review_required`는 그대로 유지한다.

## 1. Relevant Chunk 판정 기준

`relevant`는 질문에 직접 답하는 핵심 근거다. 질문의 핵심 조건, 설비, 증상, 기준, 조치가 Chunk 원문에 명시되어 있어야 한다. 검색 순위가 높거나 키워드가 겹친다는 이유만으로 `relevant`로 확정하지 않는다.

검수 질문:
- 이 Chunk만 읽어도 평가 질문의 핵심 답을 낼 수 있는가?
- `expected_answer_points`가 이 Chunk 원문에 실제로 있는가?
- 현장 상태나 수치를 새로 만들어야만 답할 수 있는가?

## 2. Partially Relevant Chunk 판정 기준

`partially_relevant`는 질문에 일부만 답하거나 배경/보조 근거를 제공하는 Chunk다. 같은 설비, 같은 증상군, 같은 기준 체계에 속하지만 질문의 직접 답이 아니면 partial로 둔다.

예: strainer 막힘 원인표는 strainer mesh 규격 질문의 배경 근거일 수 있지만, mesh 수치를 직접 말하지 않으면 `relevant`가 아니라 `partially_relevant` 또는 `irrelevant_but_confusable`일 수 있다.

## 3. Irrelevant but Confusable 판정 기준

`irrelevant_but_confusable`는 키워드가 겹쳐 검색될 수 있지만 정답으로 쓰면 안 되는 hard negative 후보를 뜻한다. 이 후보는 Retrieval 평가에서 모델이 헷갈리는지 확인하는 데 중요하다.

검수 질문:
- 같은 단어가 있지만 질문의 핵심 조건에는 답하지 못하는가?
- 다른 증상, 다른 절차, 다른 기준을 설명하고 있는가?
- 정답으로 사용하면 잘못된 답변을 유도하는가?

## 4. Unanswerable 판정 기준

`answerable=false`는 정적 RAG corpus만으로 답할 수 없는 질문이다. 미래 측정값, 현재 현장 적합/부적합 판정, 특정 기계실의 실제 일정, 실시간 계측값, 외부 API 기반 계산값은 답변 불가로 둔다.

검수 기준:
- `relevant_chunk_ids`는 비어 있어야 한다.
- 기준 설명에 도움되는 Chunk는 `partially_relevant_chunk_ids`에 둘 수 있다.
- 답변은 값을 만들지 말고 현장 기록, 계측값, 설계 입력, 실행 검증이 필요하다고 말해야 한다.

## 5. expected_answer_points 검수 기준

`expected_answer_points`는 관련 Chunk에서 확인 가능한 내용만 담아야 한다. 운영자 친화적 표현으로 바꾸는 것은 가능하지만, 원문에 없는 고장 확정, 측정값, 작업 완료 여부, 현장 상태를 추가하면 안 된다.

검수자는 각 bullet이 어떤 Chunk 문장에 대응되는지 확인한다. 대응 근거가 약하면 `reviewer_comment`에 남기고 `needs_domain_review`를 고려한다.

## 6. forbidden_claims 검수 기준

`forbidden_claims`는 답변 생성 단계의 hallucination을 막기 위한 금지 주장이다. 다음 유형이 빠져 있으면 보강을 권장한다.

- 고장 원인 확정
- 현장 점검 결과 날조
- 임의 압력/온도/용량 수치 생성
- 실시간 telemetry 또는 API 확인 주장
- 안전 기준을 위반할 수 있는 조언

## 7. label_status 변경 기준

`draft`는 아직 검수 전 상태다. `reviewed`는 사람이 relevant/partial/confusable, expected answer, forbidden claims를 검수했다는 뜻이다. `approved`는 평가 실험에 투입할 수 있을 정도로 도메인 검수와 Chunk 존재성 확인이 끝난 상태에서만 사용한다.

이 보완 작업에서는 `label_status`를 자동으로 `reviewed` 또는 `approved`로 변경하지 않는다.

## 8. 하나의 질문에 관련 Chunk가 여러 개인 경우

두 Chunk가 모두 질문의 핵심 답을 구성하면 둘 다 `relevant_chunk_ids`에 둘 수 있다. 하나는 직접 답이고 다른 하나는 배경이면 직접 답만 `relevant`, 나머지는 `partially_relevant`로 둔다.

국제 기준 비교처럼 문서 간 차이가 중요한 질문은 각 문서의 적용 맥락을 분리해서 검수한다. 서로 다른 기준의 수치를 하나의 보편 규칙처럼 합치면 안 된다.

## 9. 문서에는 답이 있지만 현재 corpus에 Chunk가 없는 경우

임의의 `chunk_id`를 만들지 않는다. `reviewer_comment` 또는 `reviewer_notes`에 `missing_corpus_chunk_candidate`를 기록하고, 가능한 경우 원문 문서명과 section을 남긴다. 다음 단계에서 corpus 재구축 또는 chunk 추가 후보로 처리한다.

## 10. 도메인 전문가 확인이 필요한 경우 표시 방법

도메인 전문가 확인이 필요하면 CSV의 `reviewer_decision`에 `needs_domain_review`를 입력하고 `reviewer_comment`에 이유를 적는다. JSONL을 수정할 때는 `reviewer_notes`에 `domain_review_required`를 추가하는 방식을 권장한다.

## 11. 판정 enum 한국어 설명

- `relevant`: 질문에 직접 답하는 핵심 근거
- `partially_relevant`: 질문에 일부만 답하거나 보조 근거
- `irrelevant`: 질문과 직접 관련 없음
- `remove`: 후보에서 제거 권장
- `add_other_chunk`: 다른 Chunk 추가 필요
- `needs_domain_review`: 도메인 전문가 검토 필요

## 12. 검수 우선순위

1. `retrieval_eval_012`
2. `retrieval_eval_014`
3. `retrieval_eval_028`
4. hard 난이도 전체
5. unanswerable 전체
6. `relevant_chunk_ids`가 여러 개인 case
7. 나머지 case
