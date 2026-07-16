# 08 Automatic Answer Evaluation

## 1. 문서 역할 안내

이 문서는 Rule-based Automatic Answer Evaluation 설계와 구현 내용을 정리한 이전 버전의 참고 문서다. 현재 단계별 절차 문서는 [04 Automatic Evaluation](./04_AUTOMATIC_EVALUATION.md)을 우선 참고한다.

실제 파일 이동은 수행하지 않았다. 향후 문서 구조를 더 정리한다면 이 문서는 `archive/` 또는 `reference/` 폴더로 이동하는 방안을 검토할 수 있다.

## 2. 목적

7.3단계에서 생성한 `answer_generation_all.jsonl` 28건을 대상으로 Rule-based Evaluation(규칙 기반 자동 평가)을 수행한다. 이 단계는 LLM Judge 전에 자동으로 확인 가능한 품질 신호를 계산하기 위한 단계다.

## 3. 평가 항목

| 항목 | 설명 |
| --- | --- |
| Expected Answer Point 포함률 | expected answer points가 답변에 포함되었는지 규칙으로 확인 |
| Forbidden Claim 탐지 | 금지 주장이 답변에 포함되었는지 확인 |
| Citation 존재 여부 | `cited_chunk_ids`가 존재하는지 확인 |
| Citation 유효성 | Citation ID가 retrieved chunk 안에 있는지 확인 |
| Retrieval Miss 정책 준수 | 근거 부족 상황에서 무리한 Citation을 하지 않았는지 확인 |
| answerable=false 처리 | 답변 불가 case에서 유보 표현을 사용하는지 확인 |
| JSON 형식 정상 여부 | 결과 JSON 구조가 정상인지 확인 |
| Warning/Error 집계 | 자동 평가 중 발견된 warning과 error를 집계 |

## 4. 생성 파일

| 파일 | 역할 |
| --- | --- |
| `rag_evaluation/automatic_evaluation/automatic_answer_eval_results.jsonl` | case별 자동 평가 결과 |
| `rag_evaluation/automatic_evaluation/automatic_answer_eval_summary.json` | 자동 평가 Summary |
| `rag_evaluation/validation/AUTOMATIC_EVALUATION_VALIDATION.md` | 검증 문서 |
| `rag_evaluation/documentation/04_AUTOMATIC_EVALUATION.md` | 현재 절차 중심 문서 |

## 5. 현재 문서와 04 문서의 차이

| 문서 | 역할 |
| --- | --- |
| `04_AUTOMATIC_EVALUATION.md` | 처음 보는 사람이 평가 절차와 결과를 이해하기 위한 현재 문서 |
| `08_AUTOMATIC_ANSWER_EVALUATION.md` | 구현 단계에서 작성된 참고/이전 버전 문서 |

## 6. 주의사항

- 이 문서는 기존 결과를 수정하지 않는다.
- 현재 공식 안내 흐름에서는 04 문서를 우선 사용한다.
- 이 문서는 삭제하지 않고 참고 문서로 유지한다.

