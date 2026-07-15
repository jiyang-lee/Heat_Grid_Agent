---
document_title: HeatGrid RAG Evaluation Policy
policy_version: 1.0-draft
status: draft
effective_date: 2026-07-14
project: HeatGrid AI Agent
owner_role: RAG Evaluation
applies_to: Retrieval Evaluation, Answer Evaluation, Human Review, Final Reporting
---

# HeatGrid RAG Evaluation Policy

## 1. 문서 목적

이 문서는 HeatGrid RAG 품질 평가의 공통 원칙을 정의한다. 평가 코드, 자동 점수, LLM Judge, 사람 검수, 최종 보고서가 같은 기준을 따르도록 하는 것이 목적이다.

HeatGrid AI Agent는 일반 대화형 챗봇이 아니라 지역난방 운영 보조 AI Agent다. 따라서 평가는 답변이 그럴듯한지보다, 운영자가 안전하고 근거 있는 판단을 할 수 있도록 돕는지에 초점을 둔다.

이 정책은 현재 완료된 RAG 감사, Retrieval 평가, Metric 검증, JSONL Retrieval Reference 평가, Answer Evaluation 설계 결과를 기준으로 작성한다. 현재 JSONL Retrieval 결과는 `dataset_status=draft`, `result_level=reference`, `official_benchmark=false`인 Draft Dataset 기반 Reference Result다.

## 2. 평가 대상과 범위

평가 대상은 다음과 같이 구분한다.

| 영역 | 평가 내용 | 현재 단계 | 향후 확장 |
|---|---|---|---|
| Retrieval 품질 | 관련 chunk를 top-k 안에 회수하는지 | 구현 및 JSONL reference 평가 완료 | pgvector 비교, top_k 비교 |
| Answer/Generation 품질 | 검색 근거로 답변을 잘 생성하는지 | 데이터셋/정책 설계 완료 | 실제 답변 생성 및 평가 |
| Citation 품질 | 답변 주장과 cited chunk가 일치하는지 | 정책/스키마 설계 완료 | citation 자동/사람 평가 |
| 운영 안전성 | 고장 단정, 현장 결과 날조, 위험 조치 방지 | rubric 설계 완료 | 사람 검수 및 승인 기준 적용 |
| Latency 및 운영 성능 | 검색/응답 지연 시간 | Retrieval latency 측정 시작 | Agent end-to-end latency |
| 자동 평가 | 규칙 기반 점수 계산 | 설계 완료 | 구현 예정 |
| LLM Judge | 의미 기반 판단 | 설계 완료 | 선택적 실행 예정 |
| 사람 검수 | 도메인 기준과 최종 승인 | rubric 설계 완료 | approved dataset 구축 |

현재 단계에서 공식적으로 실행된 것은 Retrieval reference 평가다. Answer/Generation 평가는 아직 실제 LLM 답변을 생성하지 않았으므로 설계 단계다.

## 3. 평가 우선순위

HeatGrid RAG의 공식 평가 우선순위는 다음 순서다.

1. Faithfulness
2. Hallucination Suppression
3. Operational Usefulness
4. Citation Accuracy
5. Answer Relevance

### 3.1 Faithfulness

정의: 답변의 핵심 주장이 retrieved context와 입력 데이터에서 실제로 뒷받침되는 정도다.

HeatGrid에서 중요한 이유: 운영자는 답변을 점검 판단의 참고로 사용할 수 있다. 근거와 어긋난 답변은 운영 리스크를 만든다.

좋은 답변의 예: "검색된 기준서에서는 DPV 전 스트레이너 설치 여부를 확인하도록 되어 있으므로, 해당 항목을 점검 후보로 볼 수 있습니다."

나쁜 답변의 예: "DPV 전 스트레이너가 미설치되어 있습니다." 실제 현장 확인 없이 상태를 단정한다.

자동 평가 가능 범위: citation ID 존재 여부, expected answer point의 일부 포함 여부, retrieved chunk 내 키워드 매칭.

사람 검수가 필요한 범위: 문서의 의미가 답변 주장을 충분히 뒷받침하는지, 문서 표현을 과도하게 확장했는지.

### 3.2 Hallucination Suppression

정의: 검색 근거와 입력 데이터에 없는 원인, 수치, 상태, 현장 결과, 문서 인용을 생성하지 않는 능력이다.

HeatGrid에서 중요한 이유: Hallucination은 잘못된 현장 조치나 위험 판단으로 이어질 수 있다.

좋은 답변의 예: "현재 검색된 근거만으로는 해당 기계실의 실제 통신준공 예정일을 알 수 없습니다."

나쁜 답변의 예: "S-14 기계실 통신준공 예정일은 8월 12일입니다." 입력에 없는 일정을 생성한다.

자동 평가 가능 범위: forbidden_claims 문자열/패턴 탐지, 숫자 생성 여부, citation ID 검증.

사람 검수가 필요한 범위: 의미 기반 날조, 근거보다 강한 조치로 확대 해석, 안전상 위험한 표현.

### 3.3 Operational Usefulness

정의: 운영자가 무엇을 확인하고 어떤 순서로 판단해야 하는지 이해할 수 있게 돕는 정도다.

HeatGrid에서 중요한 이유: 답변은 단순 지식 설명이 아니라 운영 보조 역할을 해야 한다.

좋은 답변의 예: "먼저 순환펌프 운전 여부와 전원 공급을 확인하고, 펌프 하우징 내 공기 여부를 확인하는 것이 문서 근거와 맞습니다."

나쁜 답변의 예: "펌프 문제일 수 있습니다." 너무 추상적이어서 다음 행동을 알기 어렵다.

자동 평가 가능 범위: 점검 동사 포함 여부, expected answer point 포함률.

사람 검수가 필요한 범위: 우선순위 적절성, 운영 맥락 적합성, 안전한 표현.

### 3.4 Citation Accuracy

정의: 답변이 참조한 chunk/document가 실제 주장과 일치하는 정도다.

HeatGrid에서 중요한 이유: citation은 운영자가 근거를 추적하는 통로다. 잘못된 citation은 근거 기반 판단을 방해한다.

좋은 답변의 예: 안전밸브 배출관 주장을 안전밸브 배출관 chunk에 연결한다.

나쁜 답변의 예: 펌프 전원 점검 주장을 급탕 온도조절 chunk에 연결한다.

자동 평가 가능 범위: cited_chunk_ids가 retrieved_chunk_ids 안에 있는지, chunk ID 형식과 존재 여부.

사람 검수가 필요한 범위: citation이 실제 주장을 의미적으로 뒷받침하는지.

### 3.5 Answer Relevance

정의: 답변이 질문에 직접 답하고 불필요한 내용 없이 초점을 유지하는 정도다.

HeatGrid에서 중요한 이유: 운영 상황에서는 짧은 시간 안에 핵심 판단이 필요하다.

좋은 답변의 예: 온수 대기시간 질문에 순환펌프 운전, 전원, 공기 확인을 중심으로 답한다.

나쁜 답변의 예: 온수 대기시간 질문에 지역난방 일반 설계 원리를 길게 설명하고 직접 점검 항목을 누락한다.

자동 평가 가능 범위: query keyword와 answer keyword overlap, expected answer point 포함률.

사람 검수가 필요한 범위: 질문 의도 충족 여부, 불필요한 장문 여부, 운영 맥락 적합성.

## 4. 좋은 답변의 정의

HeatGrid에서 좋은 답변은 다음 조건을 만족한다.

- 검색된 근거와 입력 데이터에 기반한다.
- 근거 없는 고장 확정 표현을 사용하지 않는다.
- 문서에 없는 수치나 임계값을 만들지 않는다.
- 현장 점검 결과를 날조하지 않는다.
- 불확실한 경우 가능성, 의심, 추가 확인 필요로 표현한다.
- 운영자가 다음 행동을 이해할 수 있을 정도로 구체적이다.
- 핵심 주장에 근거 chunk가 연결된다.
- 질문에 직접 답한다.
- 근거가 부족하면 답변을 유보한다.

## 5. Answer 생성 입력 정책

생성 모델에 제공하는 입력은 다음으로 제한한다.

- `query`
- `retrieved_contexts`
- 필요한 운영 안전 규칙
- 필요한 최소 metadata

생성 모델에 제공하지 않는 입력은 다음이다.

- `expected_answer_points`
- 정답 `relevant_chunk_ids`
- 평가용 human score
- 정답 label
- 평가 결과

`expected_answer_points`는 평가기에만 사용한다. 생성 모델에 정답 label 또는 평가 정답을 노출하면 답변 품질 평가가 왜곡된다. 특히 generated answer가 정답 label을 보고 만들어지면 Retrieval/Answer 평가가 독립성을 잃는다.

## 6. Citation 정책

HeatGrid Answer Evaluation은 `generated_answer`와 `cited_chunk_ids`를 분리해서 저장한다.

정책:

- `cited_chunk_ids`에는 실제 retrieved chunk만 허용한다.
- `document_id`를 `chunk_id` 대체값으로 사용하지 않는다.
- 핵심 주장마다 최소 1개 근거 연결을 원칙으로 한다.
- 불필요하게 많은 citation을 붙이지 않는다.
- citation이 실제 주장을 뒷받침하는지는 별도 평가한다.

권장 구조:

```json
{
  "generated_answer": "현재 검색된 근거에서는 순환펌프 운전 여부와 전원 공급을 먼저 확인하는 것이 적절합니다.",
  "cited_chunk_ids": [
    "danfoss_troubleshooting_table__row008"
  ]
}
```

## 7. Retrieval Hit / Miss 정책

Retrieval Hit:

- Top-5 안에 relevant chunk가 존재한다.

Retrieval Miss:

- Top-5 안에 relevant chunk가 없다.

Retrieval Miss에서는 정답처럼 단정하는 답변보다 유보 답변을 더 높게 평가한다.

권장 유보 표현:

- "현재 검색된 근거만으로는 판단하기 어렵습니다."
- "추가 문서 또는 현장 확인이 필요합니다."
- "제공된 근거에서는 해당 내용을 확인할 수 없습니다."

Retrieval Miss에서 모델의 사전 지식으로 정답을 맞힌 경우에도 RAG Grounding 성능과 분리해서 해석해야 한다. 이 경우 Answer Relevance는 높을 수 있지만 Grounding/Faithfulness 점수는 제한될 수 있다.

## 8. Hallucination 정의

다음은 Hallucination으로 본다.

- 검색 근거에 없는 원인 확정
- 고장 상태 확정
- 문서에 없는 수치 또는 임계값 생성
- 현장 확인 결과 날조
- 작업 완료 또는 회신 상태 날조
- 존재하지 않는 문서 또는 chunk 인용
- 입력에 없는 장비 상태 단정
- 문서 근거보다 강한 조치로 확대 해석

심각도:

| 수준 | 설명 | 예 |
|---|---|---|
| 경미 | 표현 과장, 불필요한 일반화 | "항상" 같은 과도한 표현 |
| 중간 | 근거 없는 점검 조치 추가 | 문서에 없는 센서 교정 권고 |
| 심각 | 고장 확정, 수치 날조, 현장 결과 날조 | "차압은 120kPa입니다" |
| 치명적 | 운영 안전에 직접 영향을 줄 수 있는 잘못된 지시 | 안전밸브 차단 허용 |

## 9. Faithfulness 판정 정책

판정 원칙:

- 모든 핵심 주장이 retrieved context에서 뒷받침되는지 확인한다.
- 문서의 "확인"을 답변에서 "교체"로 확대하지 않는다.
- 문서의 가능성을 확정 표현으로 바꾸지 않는다.
- 근거 일부만 있는 경우 부분 점수를 준다.
- 핵심 주장 대부분이 근거 없으면 낮은 점수를 준다.

사람 평가 점수는 1~5 척도를 사용하고, 최종 저장 시 0~1로 변환한다.

| 사람 점수 | 저장 점수 |
|---:|---:|
| 1 | 0.00 |
| 2 | 0.25 |
| 3 | 0.50 |
| 4 | 0.75 |
| 5 | 1.00 |

## 10. Operational Usefulness 정책

운영상 유용성은 답변이 길거나 친절한지를 평가하지 않는다.

평가 항목:

- 운영자가 무엇을 확인해야 하는지 알 수 있는가
- 조치가 근거 범위를 벗어나지 않는가
- 우선순위가 명확한가
- 필요한 경우 추가 확인을 안내하는가
- 불필요한 장문이나 중복이 없는가

운영상 유용성이 높더라도 Faithfulness 또는 Hallucination 기준을 위반하면 좋은 답변으로 승인하지 않는다.

## 11. 자동 평가 / LLM Judge / 사람 검수 역할

자동 평가:

- expected_answer_points 포함률
- forbidden_claims 규칙 검사
- citation ID 존재 여부
- cited chunk가 retrieved chunk인지
- 유보 표현 여부
- 구조 및 enum 검증

LLM Judge:

- 의미 기반 Faithfulness
- Answer Relevance
- 의미 기반 Hallucination
- Citation support 판단

사람 검수:

- 운영상 유용성
- 도메인 기준 해석
- 원인 단정 여부
- 심각한 Hallucination
- Citation이 실제 주장에 충분한지
- 최종 approved 여부

LLM Judge는 최종 정답이 아니라 참고 평가다. LLM Judge 결과와 사람 검수 결과는 분리 저장해야 한다.

## 12. Draft / Reference / Official Benchmark 정책

### Draft

- `label_status=draft`
- `review_required=true` 포함 가능
- 평가 파이프라인 시험용
- 외부 발표용 공식 성능으로 사용 금지

### Reference

- 실제 검색 또는 답변으로 계산한 참고 결과
- 데이터셋이 완전히 승인되지 않았을 수 있음
- 개선 방향 분석에 사용 가능
- 공식 Benchmark로 표현 금지

### Official Benchmark

- approved dataset 사용
- 평가 정책과 모델/Prompt/Backend 설정 고정
- 재현 가능한 실행 기록 보유
- 사람 검수 기준 충족
- 공식 보고서 또는 발표에 사용 가능

현재 JSONL Retrieval 결과는 Draft Dataset 기반 Reference Result다.

## 13. 평가 승인 기준

답변을 approved로 전환하기 위한 권장 조건:

- Faithfulness 사람 평가 4점 이상
- 심각 또는 치명적 Hallucination 없음
- Citation Accuracy 기준 충족
- 필수 안전 표현 준수
- 질문에 대한 최소 Answer Relevance 충족
- 필요한 경우 도메인 검수 완료

현재 단계에서는 자동으로 approved 처리하지 않는다.

## 14. 실패 및 보류 기준

다음 경우 승인하지 않는다.

- 근거 없는 고장 확정
- 현장 결과 날조
- 문서에 없는 임계값 또는 수치 생성
- citation이 답변을 뒷받침하지 못함
- Retrieval Miss에서 근거 있는 것처럼 답변
- 운영상 위험한 조치 권고
- 도메인 해석이 불명확한데 확정 표현 사용

다음 경우 review 보류로 둔다.

- 관련 문서 간 내용 충돌
- chunk가 불완전하게 분할됨
- 도메인 전문가 검토 필요
- RAG corpus에 필요한 문서가 없음
- 검색 결과는 있으나 질문에 직접 답하지 않음

## 15. 현재 평가 결과 해석 정책

현재 결과:

- JSONL lexical backend
- `dataset_status=draft`
- `result_level=reference`
- `official_benchmark=false`

현재 Retrieval 수치는 검색 구조의 경향 파악 및 개선 방향 제시용이다. 공식적인 최종 성능으로 표현하지 않는다.

현재 관찰된 keyword_match와 semantic_paraphrase 차이는 JSONL lexical 구조의 특성으로 해석할 수 있다. 다만 Approved Dataset과 pgvector 비교 전에는 일반화하지 않는다.

## 16. 향후 평가 단계

1. Answer Generation Runner 구현
2. 고정 Prompt/Model 설정
3. `generated_answer` 및 `cited_chunk_ids` 저장
4. 규칙 기반 자동 평가
5. LLM Judge 평가
6. 사람 검수
7. Retrieval Hit/Miss 비교
8. with_rag / no_rag 비교
9. pgvector / JSONL 비교
10. Approved Dataset 기반 Official Benchmark
11. 최종 RAG Evaluation Report

## 17. 정책 변경 관리

- 평가 정책이 변경되면 `policy_version`을 올린다.
- 기존 결과와 새 결과를 같은 기준으로 직접 비교하지 않는다.
- 모델, Prompt, Backend, top_k, Dataset이 바뀌면 실험 metadata에 기록한다.
- 정책 변경 사유와 적용 일자를 남긴다.
