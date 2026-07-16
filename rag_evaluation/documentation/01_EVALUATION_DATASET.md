# 01 Evaluation Dataset

## 1. 단계 개요

Evaluation Dataset(평가 데이터셋)은 HeatGrid RAG 평가의 기준점이다. 각 case에는 질문, 질문 의도, 난이도, answerable 여부, Gold Chunk(정답 근거 Chunk), expected answer points(기대 답변 핵심 포인트), forbidden claims(금지 주장)가 포함된다.

이 데이터셋은 Retrieval Evaluation, Answer Generation, Automatic Evaluation, LLM Judge, Manual Review가 같은 기준을 공유하도록 만든다.

## 2. 왜 필요한가?

RAG 평가는 질문에 대한 "정답 근거"가 있어야 정량화할 수 있다. 특히 Recall@K, Precision@K, MRR, nDCG는 검색 결과가 Gold Chunk를 포함하는지 비교해야 계산할 수 있다.

또한 Answer Evaluation에서는 생성 답변이 expected answer points를 얼마나 반영했는지, forbidden claims를 포함하지 않았는지 확인해야 한다.

## 3. 데이터셋 구성

| 항목 | 설명 |
| --- | --- |
| 전체 case 수 | 28 |
| answerable=false case | 3 |
| Retrieval 라벨 | `relevant_chunk_ids`, `partially_relevant_chunk_ids` |
| 답변 평가 라벨 | `expected_answer_points`, `forbidden_claims` |
| 현재 상태 | Draft/Reference 수준 |

## 4. 주요 입력 및 출력 파일

| 파일 | 역할 |
| --- | --- |
| `rag_evaluation/review/retrieval_eval.review.jsonl` | Retrieval Evaluation에 사용한 review dataset |
| `rag_evaluation/datasets/retrieval_eval.draft.jsonl` | 원본 draft dataset |
| `rag_evaluation/answer_evaluation/answer_eval.draft.jsonl` | Answer Evaluation용 draft dataset |
| `rag_evaluation/review/retrieval_eval_review.md` | 사람이 Retrieval 라벨을 검수하기 위한 Markdown |
| `rag_evaluation/review/retrieval_eval_review.csv` | case와 Chunk 조합 단위 검수 CSV |

## 5. 검수 기준

| 라벨 | 의미 |
| --- | --- |
| `relevant` | 질문의 핵심 답변을 직접 뒷받침하는 Chunk |
| `partially_relevant` | 일부 근거 또는 보조 설명은 제공하지만 핵심 답변에는 부족한 Chunk |
| `irrelevant_but_confusable` | 유사해 보이지만 정답 근거로 쓰기 어려운 Chunk |
| `unanswerable_check` | 현재 corpus 안에서 답변 가능 여부를 확인해야 하는 case |

## 6. 평가 데이터셋의 한계

- 현재 데이터셋은 사람이 최종 승인한 Official Benchmark가 아니다.
- `label_status=draft`인 case가 있으므로 결과는 Reference 수준으로 해석해야 한다.
- Gold Chunk가 누락되었거나 partially relevant 라벨이 애매한 case는 Manual Review가 필요하다.
- answerable=false case는 Retrieval metric의 macro average에서 제외되는 항목이 있다.

## 7. 재현 및 확인 방법

데이터셋 자체는 실행 대상이 아니라 정적 JSONL 파일이다. 파일 수와 case ID를 확인하려면 다음과 같이 검증 스크립트 또는 JSONL 검사 도구를 사용한다.

```bash
python rag_evaluation/scripts/run_retrieval_eval.py --help
```

실제 평가 실행은 다음 단계인 Retrieval Evaluation 문서에서 다룬다.

## 8. 관련 문서

- [Retrieval Evaluation](./02_RETRIEVAL_EVALUATION.md)
- [Answer Generation](./03_ANSWER_GENERATION.md)
- [Evaluation Report](./EVALUATION_REPORT.md)

---

## 핵심 요약

✅ 이 단계에서는 RAG 평가에 사용할 case와 Gold Chunk 라벨의 구성을 확인했다.  
✅ Retrieval부터 Answer Evaluation까지 같은 기준으로 비교하려면 기준 데이터셋이 먼저 필요하다.  
✅ 주요 결과 파일은 `rag_evaluation/review/retrieval_eval.review.jsonl`과 `rag_evaluation/answer_evaluation/answer_eval.draft.jsonl`이다.  
✅ 다음 단계는 이 데이터셋을 기준으로 Retrieval Evaluation을 수행하는 것이다.

