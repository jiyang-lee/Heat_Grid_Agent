# Rule-based Automatic Answer Evaluation Guide

## 목적

이 문서는 HeatGrid Answer Generation 결과를 규칙 기반으로 자동 점검하는 방법을 설명한다. 이번 단계는 LLM Judge나 사람 검수를 대체하지 않는다. 사람이 보기 전에 기계적으로 확인 가능한 문제를 먼저 찾는 안전망이다.

## Rule이 필요한 이유

Rule-based 평가는 빠르고 재현 가능하다. 특히 JSON 형식, citation ID 유효성, Retrieval Miss 정책, answerable=false 유보 표현, warning/error 집계처럼 의미 판단 없이 확인할 수 있는 항목에 적합하다.

## 계산 항목

| Rule | 계산 방식 | 한계 |
|---|---|---|
| Expected Answer Point 포함률 | 각 `expected_answer_points`의 주요 token이 `generated_answer`에 포함되는지 계산 | 의미적으로 같은 표현을 놓칠 수 있음 |
| Forbidden Claim 탐지 | `forbidden_claims`의 문구가 답변에 직접 포함되는지 확인 | 영어 금지 문구와 한국어 답변 간 의미 탐지는 하지 않음 |
| Citation 존재 여부 | `cited_chunk_ids`가 비어 있지 않은지 확인 | citation 의미 적합성은 판단하지 않음 |
| Citation 유효성 | 모든 `cited_chunk_ids`가 `retrieved_chunk_ids` 안에 있는지 확인 | 해당 chunk가 실제 주장을 뒷받침하는지는 판단하지 않음 |
| Retrieval Miss 정책 | Retrieval Miss에서 citation이 비어 있고 유보 표현이 있는지 확인 | Miss에서도 직접 근거가 있는 예외 상황은 사람 검토 필요 |
| answerable=false 처리 | citation이 비어 있고 유보 표현이 있는지 확인 | 부재 근거 citation의 예외는 사람 검토 필요 |
| 유보 표현 탐지 | 정해진 한국어 유보 표현이 포함되는지 확인 | 더 자연스러운 유보 표현을 놓칠 수 있음 |
| JSON 정상 여부 | case_id와 필수 구조가 유지되는지 확인 | schema 전체 검증의 보조 지표 |
| Warning/Error 집계 | 생성 결과의 `warnings`, `error`를 집계 | warning의 심각도는 별도 판단 필요 |

## 계산하지 않는 항목

다음 항목은 규칙만으로 신뢰성 있게 판단하기 어렵기 때문에 `NOT_CALCULATED`로 둔다.

- Faithfulness
- Hallucination Severity
- Operational Usefulness
- Citation Accuracy(의미적)
- Human Score
- LLM Judge Score

## 결과 해석

coverage_rate가 낮다고 곧바로 나쁜 답변이라고 판단하지 않는다. 한국어 답변과 영어 expected point 사이의 표현 차이 때문에 낮게 나올 수 있다. 반대로 coverage_rate가 높아도 Faithfulness가 보장되는 것은 아니다.

Citation valid는 ID가 유효하다는 뜻이지, citation이 의미적으로 정확하다는 뜻은 아니다. 의미적 Citation Accuracy는 다음 단계에서 LLM Judge 또는 사람 검수로 확인한다.
