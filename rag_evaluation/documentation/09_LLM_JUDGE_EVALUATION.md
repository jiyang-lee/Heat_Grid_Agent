# 09 LLM Judge Evaluation

## 1. 목적

LLM Judge 기반 의미 평가는 Rule-based Automatic Evaluation 다음 단계다. Rule-based 평가는 citation ID 유효성, warning/error, 유보 표현처럼 기계적으로 확인 가능한 항목만 계산했다. LLM Judge는 답변의 의미적 품질을 평가한다.

## 2. 평가 대상

입력 대상은 `rag_evaluation/results/answer_generation_all.jsonl` 28개 case다. Judge는 기존 생성 결과를 수정하지 않고 별도 결과 파일을 생성한다.

## 3. Generation과 Judge의 분리

Answer Generation 단계에서는 `expected_answer_points`, `forbidden_claims`, 정답 label을 사용하지 않았다. LLM Judge 단계에서는 평가자로서 이 정보를 볼 수 있다. 이는 생성 모델에게 정답을 노출하는 것이 아니라 독립적인 채점자에게 rubric을 제공하는 것이다.

## 4. 평가 항목과 점수 기준

### Faithfulness

| 점수 | 기준 |
|---:|---|
| 5 | 핵심 주장이 retrieved context에서 직접 뒷받침된다. |
| 4 | 대부분 근거 기반이며 사소한 확대만 있다. |
| 3 | 일부 핵심 주장은 근거가 있으나 일부는 약하다. |
| 2 | 상당 부분이 context 밖 추론에 의존한다. |
| 1 | context와 약하게만 관련된다. |
| 0 | 근거와 반대되거나 근거 없는 주장을 사실처럼 제시한다. |

### Hallucination Severity

| 값 | 기준 |
|---|---|
| NONE | 근거 없는 원인/수치/현장 결과/위험 지시가 없다. |
| MINOR | 경미한 일반화나 약한 추론이 있다. |
| MAJOR | 근거 없는 원인 단정, 문서 밖 조치 권고, 중요한 citation 오용이 있다. |
| CRITICAL | 안전상 위험한 지시, 임의 수치, 현장 결과 날조가 있다. |

### Operational Usefulness

| 점수 | 기준 |
|---:|---|
| 5 | 운영자가 다음 행동과 주의점을 명확히 이해할 수 있다. |
| 4 | 운영에 유용하지만 세부 우선순위가 약간 부족하다. |
| 3 | 질문에는 답하지만 실행 구체성이 부족하다. |
| 2 | 관련 정보는 있으나 행동 지침이 모호하다. |
| 1 | 일반론에 가깝다. |
| 0 | 운영상 오해나 위험을 유발한다. |

### Citation Accuracy Semantic

| 점수 | 기준 |
|---:|---|
| 5 | cited chunk가 핵심 주장을 직접 뒷받침한다. 또는 Retrieval Miss / answerable=false에서 직접 근거가 없어 빈 citation으로 적절히 유보했다. |
| 4 | 대부분 직접 뒷받침하지만 일부 주장은 citation 없이 남아 있다. |
| 3 | 관련은 있으나 보조/배경 근거에 가깝다. |
| 2 | 연결이 약하다. |
| 1 | 주제만 비슷하다. |
| 0 | 근거가 필요한 핵심 주장에 citation이 없거나 citation이 무관하다. |

빈 `cited_chunk_ids`는 그 자체로 감점하지 않는다. citation이 불필요한 상황에서 안전하게 유보한 경우 5점이 가능하다.

### Answer Relevance

| 점수 | 기준 |
|---:|---|
| 5 | 질문의 핵심 의도에 직접 답하고 불필요한 내용이 거의 없다. |
| 4 | 질문에 잘 답하지만 일부 보조 설명이 길거나 초점이 약간 넓다. |
| 3 | 질문과 관련 있고 부분적으로 답하지만 핵심 의도 일부가 부족하다. |
| 2 | 관련 정보는 있으나 질문의 핵심 답변이 약하거나 간접적이다. |
| 1 | 주제는 비슷하지만 질문에 거의 답하지 못한다. |
| 0 | 질문과 무관하거나 반대로 답한다. |

### Overall Recommendation 임시 기준

기준 상태는 `calibration_required`다.

| 값 | 임시 기준 |
|---|---|
| PASS | `faithfulness >= 4`, `citation_accuracy_semantic >= 4`, `answer_relevance >= 3`, MAJOR/CRITICAL 없음 |
| REVISE | 수정 가능한 근거, 인용, 표현 문제가 있으나 핵심 방향은 유효함 |
| FAIL | `faithfulness <= 1`, CRITICAL, 또는 운영상 위험한 MAJOR |

### Judge Confidence

| 값 | 기준 |
|---|---|
| HIGH | 근거와 답변 연결이 명확하고 채점 판단이 안정적이다. |
| MEDIUM | 대체로 판단 가능하지만 일부 citation 직접성 또는 도메인 해석이 애매하다. |
| LOW | 도메인 판단이 필요하거나 근거 연결이 불명확하다. |

## 5. 출력 파일 구조

2단계 승인 후 다음 파일을 생성한다.

- `rag_evaluation/llm_judge/llm_judge_results.jsonl`
- `rag_evaluation/llm_judge/llm_judge_summary.json`
- `rag_evaluation/validation/LLM_JUDGE_VALIDATION.md`

## 6. Summary 항목

- 평균 Faithfulness
- 평균 Operational Usefulness
- 평균 Citation Accuracy
- 평균 Answer Relevance
- Hallucination Severity 분포
- PASS / REVISE / FAIL 개수

## 7. Validation 계획

2단계 실행 후 28개 case 평가 여부, JSON parsing, schema 필드, summary 재계산, 기존 JSONL 변경 여부를 검증한다.

## 8. API 호출 전 보고 항목

2단계 실행 전 사용자에게 다음을 보고하고 승인을 받은 뒤 API를 호출한다.

- 예상 호출 수
- 예상 입력/출력 토큰
- 예상 총 토큰
- 예상 비용
- 사용할 Judge Model
- Judge Prompt Version

## 9. 다음 단계

사용자 승인 후 2단계에서 LLM Judge를 실제 실행한다. 이후 사람 검수 또는 도메인 전문가 검토와 결합해 Official Benchmark 여부를 판단한다.
