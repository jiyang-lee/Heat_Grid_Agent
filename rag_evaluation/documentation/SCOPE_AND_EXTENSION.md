# dev2-rag 기존 목표와 dev2-raglogic 확장 범위

## 1. 작업 원칙

`dev2-raglogic`은 `dev2-rag`의 기존 평가 목적과 산출물을 유지하고, 현재 대화에서 합의한 기능을 그 위에 추가한다. 기존 결과를 새 결과로 위장하거나 Mock 결과를 실제 성능으로 사용하지 않는다.

## 2. dev2-rag 기존 목표

| 목표 | 반영 상태 | 주요 산출물 |
|---|---|---|
| 현재 RAG 구조 감사 | 유지 | `CURRENT_RAG_AUDIT.md` |
| Retrieval Dataset 구성 | 유지 | `datasets/`, `review/` |
| Retrieval 정량 평가 | 유지 | Recall, Precision, HitRate, MRR, nDCG |
| 실제 RagSearcher 평가 | 현재 커밋 재실행 | `dev2_raglogic_e7c01d6_*` |
| Answer Generation | 유지 | `answer_generation_all.jsonl` |
| 규칙 기반 자동 평가 | 유지 | `automatic_evaluation/` |
| LLM Judge | 유지 | `llm_judge/` |
| 사람 수동 검토 | 유지 | `validation/LLM_JUDGE_MANUAL_REVIEW.md` |
| with-RAG/no-RAG 비교 | 실제 동일조건 평가 추가 | `RAG_CONDITION_COMPARISON.md` |

## 3. 대화에서 추가된 요구사항

| 추가 요구 | 구현 내용 |
|---|---|
| 최신 develop2 기준선 | `e7c01d6` JSONL Reference Baseline 생성 |
| Mock과 실제 결과 분리 | 실제 RagSearcher 결과에 별도 파일명 사용 |
| 실패 지점 분리 | Retrieval, Generation, Mixed, None 분류 |
| 기준선 회귀 확인 | Retrieval 실행 시 선택적 baseline gate 추가 |
| 검색 범위 확대 | 최초 Top-5, 재검토 시 Top-10과 최대 Top-20 |
| 수동 재실행 연동 | `insufficient_evidence` targeted rerun에서 broaden 전달 |
| Runtime 품질 판단 | JSONL score 및 matched terms 기반 Draft proxy |
| 프론트 제외 | 모든 변경을 평가 코드와 백엔드에 한정 |

## 4. 현재 제한사항

- Dataset은 아직 Draft이며 Approved Dataset이 아니다.
- Runtime proxy는 Draft Dataset에서 보정한 값이며 운영 승인 기준이 아니다.
- pgvector 품질 proxy는 result-count 수준이고 별도 보정이 필요하다.
- Top-10/20 확대 후 semantic reranker는 아직 구현되지 않았다.
- `rag_interpretation` stage는 상세 claim alignment가 없는 초기 구현 상태다.
- Generation과 Judge가 같은 모델이므로 자기평가 편향 가능성이 있다.
- 사람 수동 검토 결과는 전체 28건의 구조화된 최종 승인 label이 아니다.

## 5. 다음 승인 순서

1. with-RAG/no-RAG 판정 불일치 case 수동 검토
2. Retrieval label과 Answer label 승인
3. `retrieval_eval.approved.jsonl` 생성
4. Runtime proxy 재보정
5. pgvector와 JSONL 동일조건 비교
6. semantic reranker 또는 근거 선별 구현
7. Approved Dataset 기반 Official Benchmark 실행
