# with-RAG / no-RAG 비교 보고서

## 1. 목적

동일한 28개 질문과 동일한 생성 모델 및 Judge 조건에서 검색 근거 제공 여부만 바꿔 RAG 적용 전후의 답변 품질을 비교했다.

- with-RAG: Top-5 검색 문맥을 답변 모델에 제공
- no-RAG: 검색 문맥을 빈 배열로 제공
- Generation Model: `gpt-5.4-mini`
- Judge Model: `gpt-5.4-mini`
- Dataset: Draft / Reference

## 2. 실행 검증

| 항목 | with-RAG | no-RAG |
|---|---:|---:|
| 평가 case | 28 | 28 |
| Generation 실패 | 0 | 0 |
| Judge 실패 | 0 | 0 |
| 입력 context | Top-5 | 0개 |
| no-RAG citation case | 해당 없음 | 0 |

두 조건의 case ID는 28건 모두 일치한다.

## 3. 평균 점수

| 항목 | with-RAG | no-RAG | with - without |
|---|---:|---:|---:|
| Faithfulness | 3.61 | 4.21 | -0.61 |
| Operational Usefulness | 3.29 | 2.71 | +0.57 |
| Citation Accuracy | 3.29 | 4.89 | -1.61 |
| Answer Relevance | 4.04 | 3.50 | +0.54 |

RAG 적용 후 운영 유용성과 답변 적합성은 상승했다. 효과성 기준으로 17건이 개선되고 7건이 악화됐으며 4건은 같았다.

no-RAG의 Faithfulness와 Citation 점수가 높은 이유는 정답을 더 잘 답했기 때문이 아니다. 대부분의 no-RAG 답변이 근거 부족을 밝히고 판단을 유보했기 때문에 근거 없는 단정과 잘못된 citation이 줄어든 결과다.

따라서 Faithfulness와 Citation 평균만으로 RAG 적용 효과를 판단하면 안 된다. with-RAG/no-RAG 비교에서는 다음을 분리해서 해석한다.

- 효과성: Operational Usefulness, Answer Relevance
- 근거 안전성: Faithfulness, Hallucination, Citation Accuracy
- 검색 기여도: Retrieval Hit/Miss

## 4. Recommendation 분포

| Recommendation | with-RAG | no-RAG |
|---|---:|---:|
| PASS | 16 | 18 |
| REVISE | 10 | 10 |
| FAIL | 2 | 0 |

no-RAG PASS가 더 많은 것도 유보 답변에 대한 안전성 판정 영향이 크다. PASS 개수만으로 RAG가 불필요하다고 결론 내릴 수 없다.

## 5. 실패 원인 분리

기존 with-RAG 결과를 Retrieval과 Generation으로 분리한 Reference 판정은 다음과 같다.

| 실패 원인 | case 수 |
|---|---:|
| 정상 | 8 |
| Retrieval | 12 |
| Generation | 5 |
| Mixed | 3 |

검색 성공 후 답변이 낮게 평가된 case는 Generation 문제로, 검색 실패 후 안전하게 유보한 case는 Retrieval 문제로, 검색 실패와 생성 오류가 함께 나타난 case는 Mixed 문제로 분류한다.

## 6. 수동 검토

두 조건의 Recommendation 또는 Hallucination 판정이 달라진 17건은 우선 수동 검토 대상이다. 현재 Generation과 Judge에 동일 모델을 사용했기 때문에 사람 검수 또는 다른 모델 계열의 Cross-model Judge가 필요하다.

## 7. 결론

현재 RAG는 평균적으로 답변의 운영 유용성과 질문 적합성을 높였지만 모든 case에서 개선되지는 않았다. 검색 실패와 문서 해석 실패를 분리하고, 악화된 7건과 판정 불일치 17건을 검토해야 한다.

이 결과는 Draft Dataset 기반 Reference Result이며 공식 Benchmark가 아니다.
