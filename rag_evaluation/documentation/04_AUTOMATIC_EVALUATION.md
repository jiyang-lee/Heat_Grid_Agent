# 04 Automatic Evaluation

## 1. 단계 개요

Automatic Evaluation(자동 평가)은 Answer Generation 결과를 Rule-based Evaluation(규칙 기반 자동 평가)으로 점검하는 단계다. 이 단계에서는 LLM Judge나 사람 평가를 사용하지 않고, 코드 규칙으로 확인 가능한 항목만 계산한다.

## 2. 왜 진행하는가?

LLM Judge는 의미 평가에 강하지만, 모든 품질 검사를 LLM에게 맡길 필요는 없다. JSON 형식, Citation ID, Forbidden Claim(금지 주장), 내부 Label Leak(정답 라벨 누수)처럼 규칙으로 판단 가능한 항목은 자동 검사로 빠르고 일관되게 확인할 수 있다.

## 3. Rule-based Evaluation이 필요한 이유

Rule-based Evaluation은 의미를 해석하지는 못하지만, 구조적 오류와 정책 위반을 안정적으로 찾는다. 이는 LLM Judge 전에 전체 결과를 깨끗하게 정리하는 품질 게이트 역할을 한다.

| 구분 | Rule-based Evaluation | LLM Judge |
| --- | --- | --- |
| 주요 목적 | 형식, ID, 정책 위반 여부를 기계적으로 검사 | 답변 의미, 근거 충실성, 운영 유용성 평가 |
| 강점 | 빠름, 재현 가능, 동일 입력에 항상 같은 결과 | 문맥과 의미를 해석할 수 있음 |
| 한계 | 의미적 Faithfulness나 Hallucination 판정은 어려움 | 비용이 들고 모델 편향 가능성이 있음 |
| HeatGrid 내 역할 | 전체 28개 case의 기초 품질 게이트 | Rule-based로 잡기 어려운 의미 품질 평가 |

## 4. 평가 항목

| 항목 | 설명 |
| --- | --- |
| `coverage_rate` | expected answer points가 답변에 포함되었는지 문자열 규칙으로 계산 |
| `forbidden_claim_detected` | forbidden claims가 답변에 등장했는지 탐지 |
| `citation_exists` | Citation이 존재하는지 확인 |
| `citation_valid` | Citation ID가 실제 retrieved chunk 안에 있는지 확인 |
| `retrieval_miss_policy_passed` | Retrieval Miss에서 무리한 Citation을 하지 않았는지 확인 |
| `answerable_policy_passed` | answerable=false case에서 유보 정책을 지켰는지 확인 |
| `json_valid` | JSON 구조가 정상인지 확인 |
| `warning_count`, `error_count` | warning과 error 집계 |

## 5. 계산하지 않는 항목

다음 항목은 Rule-based로 의미를 판정하기 어렵기 때문에 `NOT_CALCULATED`로 남겼다.

- Faithfulness
- Hallucination Severity
- Operational Usefulness
- Citation Accuracy Semantic
- Human Score
- LLM Judge Score

## 6. 주요 입력 및 출력 파일

| 파일 | 역할 |
| --- | --- |
| `rag_evaluation/results/answer_generation_all.jsonl` | 평가 대상 Answer Generation 결과 |
| `rag_evaluation/answer_evaluation/answer_eval.draft.jsonl` | expected answer points와 forbidden claims |
| `rag_evaluation/automatic_evaluation/automatic_answer_eval_results.jsonl` | case별 자동 평가 결과 |
| `rag_evaluation/automatic_evaluation/automatic_answer_eval_summary.json` | 자동 평가 Summary |
| `rag_evaluation/validation/AUTOMATIC_EVALUATION_VALIDATION.md` | 검증 문서 |

## 7. 현재 결과 요약

기존 Summary 파일 기준 결과는 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| 전체 case 수 | 28 |
| 평균 coverage | 0.10714285714285714 |
| Citation valid ratio | 1.0 |
| Forbidden claim 발생 건수 | 0 |
| Retrieval Miss policy pass ratio | 1.0 |
| answerable=false pass ratio | 1.0 |
| warning total | 8 |
| error total | 0 |
| JSON valid count | 28 |

## 8. Coverage 해석 주의

`coverage_rate`는 semantic matching이 아니라 문자열 기반 rule matching이다. expected answer points와 generated answer의 언어, 표현 방식, 인코딩 이슈가 다르면 coverage가 낮게 계산될 수 있다. 따라서 coverage가 낮다고 해서 반드시 답변 품질이 낮다는 뜻은 아니다.

## 9. 실행 방법

```bash
python rag_evaluation/scripts/run_automatic_answer_eval.py
```

## 10. 관련 문서

- [Answer Generation](./03_ANSWER_GENERATION.md)
- [LLM Judge](./05_LLM_JUDGE.md)
- [Evaluation Report](./EVALUATION_REPORT.md)

---

## 핵심 요약

✅ 이 단계에서는 생성 답변의 형식, Citation, 정책 위반 여부를 규칙으로 자동 점검했다.  
✅ LLM Judge 전에 명확한 오류를 빠르게 걸러내면 평가 비용과 검수 부담을 줄일 수 있다.  
✅ 주요 결과 파일은 `rag_evaluation/automatic_evaluation/automatic_answer_eval_results.jsonl`과 Summary 파일이다.  
✅ 다음 단계는 Rule-based로 판단하기 어려운 의미 품질을 LLM Judge로 평가하는 것이다.

