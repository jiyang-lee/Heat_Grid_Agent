# Dataset Review Checklist

## Case-Level Checklist

- [ ] 운영자 질문으로 자연스러운가.
- [ ] 질문 의도(`query_intent`)와 질문 유형(`query_type`)이 실제 질문과 맞는가.
- [ ] Relevant Chunk가 질문에 직접 답하는가.
- [ ] Chunk ID가 실제 `data/rag_sources/metadata/rag_chunks.jsonl`에 존재하는가.
- [ ] Relevant와 Partially Relevant가 구분되는가.
- [ ] Irrelevant but Confusable chunk가 hard negative로 적절한가.
- [ ] `expected_answer_points`가 문서 근거와 일치하는가.
- [ ] `forbidden_claims`가 고장 확정, 현장 결과 날조, 임의 수치 생성 등을 막기에 충분한가.
- [ ] `answerable=false` 질문은 정적 코퍼스로 답할 수 없다는 점이 명확한가.
- [ ] 특정 Fault Group이나 특정 문서에 과도하게 편중되지 않았는가.
- [ ] 검수 전 row의 `label_status`가 `draft`인가.
- [ ] 검수가 필요한 경우 `reviewer_notes`에 이유가 기록되었는가.

## High-Priority Review Items

- [ ] `retrieval_eval_012`: strainer priority 질문은 PDF extraction이 충분히 strainer-specific evidence를 보존했는지 확인한다.
- [ ] `retrieval_eval_014`: IEA strainer mesh와 Swedish F:101 filter mesh 기준을 같은 기준으로 혼합하지 않았는지 확인한다.
- [ ] `retrieval_eval_023`: comparison 질문이 `category=operating_standard`, `query_intent=comparison`으로 분류된 것이 분석 목적에 맞는지 확인한다.
- [ ] `retrieval_eval_028`: 설계 계산/미래 날씨 질문이 hard unanswerable로 적절한지 확인한다.

## Approval Checklist

- [ ] 모든 `relevant_chunk_ids` 존재성 검사를 통과했다.
- [ ] 모든 JSONL 행이 JSON 파싱을 통과했다.
- [ ] 사람이 relevant/partial/confusable을 최소 1회 검수했다.
- [ ] `review_required=false` 또는 `label_status=approved`로 승격할 case만 자동 평가에 포함한다.
- [ ] `answerable=false` case는 Recall@K 계산에서 제외할지, no-answer retrieval 평가로 별도 집계할지 결정했다.
