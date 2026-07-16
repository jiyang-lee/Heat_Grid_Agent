# Answer Evaluation Readiness

## 준비 상태 표

| 항목 | 상태 | 현재 사용 가능한 데이터 | 부족한 데이터 | 필요한 최소 추가 작업 | 우선순위 |
|---|---|---|---|---|---|
| 실제 LLM 답변 생성 가능 여부 | 일부 가능 | query, retrieved_contexts, expected_answer_points | answer prompt, model config, generated answer 저장 로직 | answer generation runner 작성 | 높음 |
| Agent 기존 출력 재사용 가능 여부 | 추가 구현 필요 | 현재 retrieval 평가 결과 | case_id와 Agent output 매핑 | 기존 agent run log와 case 매핑 확인 | 중간 |
| retrieved context 저장 충분 여부 | 가능 | raw_retrieval_outputs 기반 top-5 context | citation span 수준 정보 | 현재는 chunk 단위 평가로 시작 | 높음 |
| Citation 평가 가능 여부 | 일부 가능 | retrieved_chunk_ids, retrieved_contexts | generated_answer 내 citation format | 답변 prompt에 citation 형식 강제 | 높음 |
| Faithfulness 자동 평가 가능 여부 | 일부 가능 | context와 answer 저장 구조 | generated_answer, LLM Judge rubric | judge prompt 설계 | 중간 |
| Hallucination 자동 평가 가능 여부 | 일부 가능 | forbidden_claims, context | generated_answer, judge/human labels | 규칙 + judge + human review 구성 | 높음 |
| 사람 검수 필요 여부 | 가능 | rubric, expected/forbidden claims | 실제 답변 | review sheet 또는 UI | 높음 |
| OpenAI API 호출 비용 추정 가능 여부 | 추가 구현 필요 | case 수, context 길이 | model, prompt token count | token estimator 또는 dry-run prompt 생성 | 중간 |
| with_rag / no_rag 비교 가능 여부 | 추가 구현 필요 | answer eval schema | no_rag answer 생성 결과 | 두 조건의 answer 저장 필드 추가 | 중간 |
| Retrieval Hit / Miss 비교 가능 여부 | 가능 | retrieval_hit_at_5, query_type, answerable | generated answer scores | score 계산 후 group breakdown | 높음 |

## 현재 결론

Answer Evaluation 설계와 데이터셋 확장은 준비됐다. 실제 품질 평가는 아직 `generated_answer`가 없으므로 수행할 수 없다. 다음 단계의 최소 작업은 동일 prompt 기준으로 `generated_answer`와 `cited_chunk_ids`를 생성하고, 규칙 기반 자동 점수부터 계산하는 것이다.

## 반드시 유지할 Metadata

- `dataset_status=draft`
- `result_level=reference`
- `official_benchmark=false`

현재 Answer 평가도 Official Benchmark가 아니다.
