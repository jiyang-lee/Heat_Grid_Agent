# 08 Automatic Answer Evaluation

## 1. 이번 단계의 목적

7.3단계에서 생성한 `answer_generation_all.jsonl` 28건을 대상으로 Rule-based Automatic Answer Evaluation을 수행한다. 이번 단계는 LLM Judge와 사람 평가 이전에 자동으로 확인 가능한 품질 신호를 계산하는 단계다.

## 2. 왜 Rule-based 평가를 먼저 하는가

Rule-based 평가는 빠르고 재현 가능하며 비용이 들지 않는다. JSON 구조, citation ID 유효성, warning/error 여부, Retrieval Miss 정책 준수처럼 명확한 규칙으로 판단 가능한 항목을 먼저 걸러내면 이후 LLM Judge와 사람 검수의 부담을 줄일 수 있다.

## 3. 평가 항목 설명

자동 평가는 다음 항목을 계산한다.

- Expected Answer Point 포함률
- Forbidden Claim 직접 탐지
- Citation 존재 여부
- Citation이 실제 retrieved chunk인지 여부
- Retrieval Miss 정책 준수 여부
- answerable=false 처리 여부
- 유보 표현 존재 여부
- JSON 형식 정상 여부
- Warning 집계
- Error 집계

## 4. 계산 가능한 항목

문자열, 리스트, boolean, ID 집합 비교로 확인할 수 있는 항목만 계산한다. 예를 들어 `cited_chunk_ids`가 `retrieved_chunk_ids` 안에 있는지는 자동으로 계산할 수 있다.

## 5. 아직 계산하지 않는 항목

다음 항목은 의미 판단이 필요하므로 이번 단계에서 계산하지 않는다.

- Faithfulness
- Hallucination Severity
- Operational Usefulness
- Citation Accuracy(의미적)
- Human Score
- LLM Judge Score

## 6. 입력 파일

- `rag_evaluation/results/answer_generation_all.jsonl`
- `rag_evaluation/answer_evaluation/answer_eval.draft.jsonl`

## 7. 출력 파일

- `rag_evaluation/automatic_evaluation/automatic_answer_eval_results.jsonl`
- `rag_evaluation/automatic_evaluation/automatic_answer_eval_summary.json`
- `rag_evaluation/validation/AUTOMATIC_EVALUATION_VALIDATION.md`

## 8. 생성되는 결과

각 case에는 `rule_evaluation`과 `quality_status`가 저장된다. `rule_based_completed=true`, `llm_judge_completed=false`, `human_review_completed=false`로 기록한다.

## 9. 다음 단계

다음 단계는 LLM Judge 기반 평가다. Rule-based 결과에서 발견된 warning, 낮은 coverage, citation 문제 후보를 참고해 Faithfulness, Hallucination, Operational Usefulness, 의미적 Citation Accuracy를 평가한다.
