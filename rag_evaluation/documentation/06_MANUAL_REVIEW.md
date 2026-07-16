# 06 Manual Review

## 1. 단계 개요

Manual Review(수동 검토)는 LLM Judge 결과를 사람이 다시 확인하는 단계다. 이 단계에서는 원본 Retrieval 결과, generated answer, Citation, Automatic Evaluation 결과, LLM Judge 점수와 rationale을 함께 비교한다.

중요한 원칙은 Judge 결과를 직접 수정하지 않는 것이다. 문제 가능성은 별도 검토 문서에 기록하고, 원본 JSON/JSONL 결과는 보존한다.

## 2. 왜 필요한가?

LLM Judge는 빠르고 일관된 평가에 유용하지만, 다음 한계가 있다.

- Generation과 Judge가 같은 모델일 때 Self-preference Bias(자기 선호 편향)가 생길 수 있다.
- Citation 문제를 답변 전체 실패로 과도하게 해석할 수 있다.
- Retrieval Miss 상황에서 유보 답변을 낮게 평가하거나 높게 평가하는 기준이 흔들릴 수 있다.
- 도메인 지식이 필요한 case는 LLM 판단만으로 확정하기 어렵다.

## 3. 검토 대상

Manual Review에서는 전체 28건 중 우선 검토 case와 최고 점수 기준 case를 중심으로 확인했다.

| 유형 | 예시 case |
| --- | --- |
| 우선 검토 case | `retrieval_eval_006`, `retrieval_eval_008`, `retrieval_eval_016` 등 |
| Retrieval Miss 검토 | `retrieval_eval_002`, `retrieval_eval_003` 등 |
| 최고 점수 기준 사례 | `retrieval_eval_001`, `retrieval_eval_021` |

## 4. 검토 기준

| 기준 | 확인 내용 |
| --- | --- |
| Judge 내부 일관성 | 점수, hallucination 판정, final verdict가 서로 맞는지 |
| 근거 기반 타당성 | 핵심 주장이 retrieved evidence로 뒷받침되는지 |
| 오류 분리 | Retrieval 실패와 Generation 실패를 구분했는지 |
| 동일 모델 편향 | Judge가 같은 모델의 답변을 과도하게 선호하지 않았는지 |

## 5. 문제 유형 분류

Manual Review에서는 문제를 다음 유형으로 분류했다.

| 유형 | 의미 |
| --- | --- |
| `RETRIEVAL_FAILURE` | 필요한 근거가 검색되지 않음 |
| `GENERATION_FAILURE` | 검색 근거가 있어도 답변 생성이 부정확함 |
| `CITATION_FAILURE` | 답변과 Citation 연결이 부정확함 |
| `JUDGE_INCONSISTENCY` | Judge 점수와 rationale 또는 verdict가 일관되지 않음 |
| `DATASET_LABEL_ISSUE` | Gold Chunk 또는 라벨 자체가 재검토 필요 |
| `NO_MATERIAL_ISSUE` | 큰 문제 없음 |
| `MULTIPLE` | 여러 문제가 함께 존재 |

## 6. 주요 산출물

| 파일 | 역할 |
| --- | --- |
| `rag_evaluation/validation/LLM_JUDGE_MANUAL_REVIEW.md` | case별 수동 검토 결과 |
| `rag_evaluation/llm_judge/llm_judge_results.jsonl` | 검토 대상 Judge 원본 결과 |
| `rag_evaluation/automatic_evaluation/automatic_answer_eval_results.jsonl` | Rule-based 결과 |
| `rag_evaluation/results/real_retrieval_results.jsonl` | Retrieval 결과 |

## 7. 해석

Manual Review는 새로운 점수를 생성하지 않는다. 대신 Judge 판정을 그대로 유지할 case, 재검토가 필요한 case, 상위 모델 또는 다른 계열 모델로 재평가할 최소 case를 분리한다.

이 단계의 목적은 LLM Judge 결과를 공식 판정으로 확정하는 것이 아니라, 운영 적용 전 리스크를 명확히 드러내는 것이다.

## 8. 한계

- 전체 case를 사람 평가자가 독립 채점한 것은 아니다.
- 검토는 우선순위 case 중심으로 수행되었다.
- 도메인 전문가가 최종 판단해야 하는 case가 남을 수 있다.
- Cross-model Judge는 Future Work이며 현재 수행된 결과로 작성하지 않는다.

## 9. 관련 문서

- [LLM Judge](./05_LLM_JUDGE.md)
- [Evaluation Report](./EVALUATION_REPORT.md)

---

## 핵심 요약

✅ 이 단계에서는 LLM Judge 결과가 evidence 기준으로 타당한지 사람이 다시 검토했다.  
✅ 동일 모델 편향, Citation 과대 감점, Retrieval Miss 해석 오류를 줄이기 위해 필요하다.  
✅ 주요 결과 파일은 `rag_evaluation/validation/LLM_JUDGE_MANUAL_REVIEW.md`이다.  
✅ 다음 단계는 필요 시 Cross-model Judge 또는 Human Evaluation으로 재검증하는 것이다.

