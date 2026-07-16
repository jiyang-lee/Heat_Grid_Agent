# 09 LLM Judge Evaluation

## 1. 문서 역할 안내

이 문서는 LLM Judge Rubric(채점 기준)과 설계 배경을 설명하는 참고 문서다. 현재 단계별 절차와 실행 결과 중심 문서는 [05 LLM Judge](./05_LLM_JUDGE.md)를 우선 참고한다.

파일명 변경은 수행하지 않았다. 다만 이 문서의 실제 역할은 Rubric 설계 참고 문서에 가까우므로, 향후 문서 구조 정리 시 `09_LLM_JUDGE_RUBRIC.md`로 이름을 바꾸는 방안을 제안할 수 있다.

## 2. 평가 목적

LLM Judge는 Rule-based Evaluation으로 판단하기 어려운 의미 기반 품질을 평가한다. Judge는 생성 답변, 검색 근거, Citation, expected answer points, forbidden claims를 함께 보고 답변 품질을 채점한다.

Generation 단계에서는 hidden label을 사용하지 않았고, Judge 단계에서만 평가자로서 expected answer points와 forbidden claims를 볼 수 있다.

## 3. 평가 항목

| 항목 | 값 범위 | 설명 |
| --- | --- | --- |
| Faithfulness | 0~5 | 답변이 retrieved context에 충실한지 |
| Hallucination Severity | `NONE`, `MINOR`, `MAJOR`, `CRITICAL` | 근거 없는 생성의 심각도 |
| Operational Usefulness | 0~5 | 운영자가 실제로 참고할 수 있는지 |
| Citation Accuracy Semantic | 0~5 | Citation이 답변 주장과 의미적으로 연결되는지 |
| Answer Relevance | 0~5 | 질문에 직접 답하는지 |
| Overall Recommendation | `PASS`, `REVISE`, `FAIL` | 종합 권고 |
| Judge Confidence | `HIGH`, `MEDIUM`, `LOW` | Judge 판단 신뢰도 |

## 4. Citation Accuracy 기준

Citation이 항상 많을수록 좋은 것은 아니다. answerable=false 또는 Retrieval Miss에서 직접 근거가 없어 `cited_chunk_ids=[]`로 유보한 경우는 낮은 점수를 주지 않는다.

감점은 근거가 필요한 핵심 주장에 Citation이 없거나, Citation이 실제 retrieved chunk와 의미적으로 연결되지 않을 때 적용한다.

## 5. Overall Recommendation 기준

| 권고 | 기준 |
| --- | --- |
| `PASS` | Faithfulness와 Citation Accuracy가 충분하고, MAJOR/CRITICAL hallucination이 없음 |
| `REVISE` | 근거, Citation, 표현 문제는 있지만 수정 가능 |
| `FAIL` | Faithfulness가 매우 낮거나 운영상 위험한 hallucination이 있음 |

현재 기준은 `calibration_required` 상태다. 즉, 향후 Human Evaluation 또는 Cross-model Judge로 보정할 수 있다.

## 6. 현재 문서와 05 문서의 차이

| 문서 | 역할 |
| --- | --- |
| `05_LLM_JUDGE.md` | 전체 평가 흐름에서 LLM Judge 단계가 무엇을 했는지 설명 |
| `09_LLM_JUDGE_EVALUATION.md` | Judge Rubric과 설계 기준을 참고용으로 설명 |

## 7. 주의사항

- 이 문서는 기존 Judge 결과를 수정하지 않는다.
- 현재 절차 안내에서는 05 문서를 우선 사용한다.
- Cross-model Judge는 Future Work이며 실제 수행된 결과로 작성하지 않는다.

