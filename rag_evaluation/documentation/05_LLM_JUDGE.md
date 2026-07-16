# 05 LLM Judge

## 1. 단계 개요

LLM Judge(대규모 언어 모델 기반 평가)는 생성 답변과 retrieved context를 함께 보고 의미 기반 품질을 평가하는 단계다. Automatic Evaluation이 규칙으로 확인하기 어려운 Faithfulness(근거 충실성), Hallucination Severity(환각 심각도), Operational Usefulness(운영 유용성), Citation Accuracy Semantic(Citation 의미 정확도), Answer Relevance(질문 관련성)를 평가한다.

## 2. 왜 진행하는가?

Rule-based Evaluation은 JSON 형식이나 Citation ID 유효성처럼 명확한 규칙은 잘 확인한다. 하지만 답변이 실제 근거에 충실한지, 근거에 없는 내용을 단정했는지, Citation이 주장과 의미적으로 연결되는지는 의미 해석이 필요하다.

LLM Judge는 이 의미 평가를 빠르고 일관된 기준으로 수행하기 위해 사용했다.

## 3. 왜 사람이 아닌 LLM Judge를 사용하는가?

Human Evaluation(사람 평가)은 가장 정확할 수 있지만 비용과 시간이 많이 들고, 동일 기준으로 반복 평가하기 어렵다. LLM Judge는 빠르고 일관된 1차 의미 평가를 수행하기 위한 도구이며, 28개 case 전체를 같은 Rubric(채점 기준)으로 비교하는 데 유용하다.

다만 LLM Judge가 사람 평가를 완전히 대체하는 것은 아니다. HeatGrid에서는 Self-preference Bias(자기 선호 편향)와 Judge Calibration(평가 기준 보정) 문제를 줄이기 위해 Manual Review를 추가로 수행했다.

## 4. Judge 설정

| 항목 | 값 |
| --- | --- |
| Judge Model | `gpt-5.4-mini` |
| Judge Prompt Version | `llm-judge-v1.0-draft` |
| Generation Model | `gpt-5.4-mini` |
| Temperature | 0 |
| 평가 case 수 | 28 |
| recommendation 기준 상태 | `calibration_required` |

## 5. 평가 항목

| 항목 | 값 범위 | 의미 |
| --- | --- | --- |
| `faithfulness` | 0~5 | 답변이 retrieved context에 근거했는지 |
| `hallucination_severity` | `NONE`, `MINOR`, `MAJOR`, `CRITICAL` | 근거 없는 생성의 심각도 |
| `operational_usefulness` | 0~5 | 운영자가 실제로 참고할 수 있는 답변인지 |
| `citation_accuracy_semantic` | 0~5 | Citation이 답변 주장과 의미적으로 연결되는지 |
| `answer_relevance` | 0~5 | 질문에 얼마나 직접 답했는지 |
| `overall_recommendation` | `PASS`, `REVISE`, `FAIL` | 종합 권고 |
| `judge_confidence` | `HIGH`, `MEDIUM`, `LOW` | Judge 판단 신뢰도 |

## 6. 주요 입력 및 출력 파일

| 파일 | 역할 |
| --- | --- |
| `rag_evaluation/results/answer_generation_all.jsonl` | Judge 평가 대상 |
| `rag_evaluation/llm_judge/llm_judge_results.jsonl` | case별 LLM Judge 결과 |
| `rag_evaluation/llm_judge/llm_judge_summary.json` | 전체 Summary |
| `rag_evaluation/validation/LLM_JUDGE_VALIDATION.md` | 실행 검증 문서 |
| `rag_evaluation/validation/LLM_JUDGE_MANUAL_REVIEW.md` | Manual Review 결과 |

## 7. 현재 결과 요약

기존 Summary 파일 기준 결과는 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| 평가 case 수 | 28 |
| 실패 case 수 | 0 |
| Faithfulness 평균 | 3.607142857142857 |
| Operational Usefulness 평균 | 3.2857142857142856 |
| Citation Accuracy Semantic 평균 | 3.2857142857142856 |
| Answer Relevance 평균 | 4.035714285714286 |
| 총 token | 125297 |
| 추정 비용 | null |

| 분포 | 값 |
| --- | --- |
| Hallucination | `NONE`: 16, `MINOR`: 11, `MAJOR`: 1 |
| Overall Recommendation | `PASS`: 16, `REVISE`: 10, `FAIL`: 2 |
| Judge Confidence | `HIGH`: 27, `MEDIUM`: 1 |

## 8. 동일 모델 평가의 한계

Generation과 Judge가 모두 `gpt-5.4-mini`이다. 같은 계열 모델이 자신의 답변 스타일이나 유보 표현을 더 관대하게 평가할 가능성이 있다. 이 한계를 보완하기 위해 Manual Review에서 evidence 기준으로 일부 case를 다시 검토했다.

## 9. 실행 방법

사전 계획 확인:

```bash
python rag_evaluation/scripts/run_llm_judge.py --plan-only
```

승인 후 전체 실행:

```bash
python rag_evaluation/scripts/run_llm_judge.py
```

API Key 값은 출력하지 않는다.

## 10. 관련 문서

- [Automatic Evaluation](./04_AUTOMATIC_EVALUATION.md)
- [Manual Review](./06_MANUAL_REVIEW.md)
- [Evaluation Report](./EVALUATION_REPORT.md)

---

## 핵심 요약

✅ 이 단계에서는 Faithfulness, Hallucination, 운영 유용성, Citation 의미 정확도를 LLM Judge로 평가했다.  
✅ Rule-based Evaluation만으로는 답변 의미와 근거 충실성을 판단하기 어렵기 때문에 필요하다.  
✅ 주요 결과 파일은 `rag_evaluation/llm_judge/llm_judge_results.jsonl`과 `rag_evaluation/llm_judge/llm_judge_summary.json`이다.  
✅ 다음 단계는 LLM Judge 결과의 편향과 일관성을 Manual Review로 검토하는 것이다.

