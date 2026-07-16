# 02 Retrieval Evaluation

## 1. 단계 개요

Retrieval Evaluation(검색 평가)은 질문에 필요한 Gold Chunk(정답 근거 Chunk)를 검색 결과 안에서 찾았는지 측정하는 단계다. HeatGrid의 현재 Retrieval은 OpenAI Embedding 기반 Semantic Retrieval(의미 기반 검색)이 아니라, hash embedding 기반 pgvector 검색과 JSONL Lexical Search(키워드 기반 검색) fallback 구조를 가진다.

이번 평가에서는 실제 실행 결과가 모두 JSONL backend로 처리되었다.

## 2. 왜 필요한가?

RAG에서 답변 모델이 아무리 좋아도 필요한 근거가 검색되지 않으면 정확한 답변을 만들기 어렵다. Retrieval Evaluation은 Answer Generation 전에 다음을 확인한다.

- 검색 결과 Top-K 안에 Gold Chunk가 들어오는가
- 검색 결과가 너무 넓거나 노이즈가 많지 않은가
- Retrieval Hit와 Retrieval Miss가 Answer 품질에 어떤 차이를 만드는가
- 현재 fallback 구조가 reference 평가 수준에서 어느 정도 동작하는가

## 3. 평가 Metric

| Metric | 쉬운 설명 | 현재 계산 여부 |
| --- | --- | --- |
| Recall@K | 정답 근거를 Top-K 안에서 찾았는지 | 계산 |
| Precision@K | Top-K 결과 중 실제 관련 Chunk 비율 | 계산 |
| HitRate@K | 정답 근거가 하나라도 검색된 case 비율 | 계산 |
| MRR | 첫 정답 Chunk가 몇 번째에 나왔는지 | 계산 |
| nDCG@K | 관련도와 순위를 함께 반영한 검색 품질 | 계산 |
| Latency | 검색 소요 시간 | 계산 |

초보자를 위한 간단한 예시는 다음과 같다.

```text
질문: "스트레이너 막힘 시 어떤 점검을 해야 하는가?"

검색 결과 Top-5:
1. chunk_A
2. chunk_B
3. chunk_GOLD   <- Gold Chunk(정답 근거 Chunk)
4. chunk_C
5. chunk_D

해석:
- 정답 Chunk가 Top-5 안에 있으므로 Recall@5는 성공
- 정답 Chunk가 3번째에 있으므로 MRR은 1/3
- Top-5 중 정답 Chunk가 1개라면 Precision@5는 1/5
```

## 4. 실행 방법

실행 명령은 다음 구조를 사용한다.

```bash
python rag_evaluation/scripts/run_real_retrieval_eval.py --help
```

실제 평가에서는 서버, Docker, DB를 새로 실행하지 않고 JSONL fallback 결과를 기준으로 평가했다.

## 5. 주요 입력 및 출력 파일

| 파일 | 역할 |
| --- | --- |
| `rag_evaluation/review/retrieval_eval.review.jsonl` | 평가 입력 dataset |
| `rag_evaluation/results/real_retrieval_results.jsonl` | case별 실제 Retrieval 결과 |
| `rag_evaluation/results/real_retrieval_summary.json` | Retrieval metric summary |
| `rag_evaluation/validation/REAL_RETRIEVAL_RESULT_CHECK.md` | 결과 검증 문서 |

## 6. 현재 결과 요약

기존 Summary 파일 기준 결과는 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| 전체 case 수 | 28 |
| 평가 대상 answerable case | 25 |
| 제외된 unanswerable case | 3 |
| actual backend | `jsonl` 28건 |
| Recall@1 | 0.28 |
| Recall@3 | 0.36 |
| Recall@5 | 0.4 |
| Precision@1 | 0.28 |
| Precision@3 | 0.12 |
| Precision@5 | 0.08 |
| MRR | 0.32333333333333336 |
| nDCG@5 | 0.29054645946376806 |
| 평균 latency ms | 16.78571428471644 |
| p95 latency ms | 31.00000019185245 |

## 7. 해석

Recall@5가 0.4라는 것은 answerable case 중 40%에서 Gold Chunk가 Top-5 안에 들어왔다는 뜻이다. 이 결과는 현재 JSONL lexical fallback 구조의 기준 성능으로 볼 수 있다.

다만 이 값은 Official Benchmark가 아니라 Reference 결과다. 데이터셋 라벨이 아직 draft/review 상태이며, Semantic Retrieval과 동일 기준으로 단순 비교해서는 안 된다.

## 8. 한계

- 현재 실행은 JSONL backend 기준이다.
- pgvector backend와 직접 비교한 결과는 아니다.
- hash embedding과 lexical fallback은 의미적 paraphrase 검색에 한계가 있을 수 있다.
- Retrieval Miss는 Generation 품질 저하로 이어질 수 있다.

## 9. 관련 문서

- [Evaluation Dataset](./01_EVALUATION_DATASET.md)
- [Answer Generation](./03_ANSWER_GENERATION.md)
- [Evaluation Report](./EVALUATION_REPORT.md)

---

## 핵심 요약

✅ 이 단계에서는 Retrieval 결과가 Gold Chunk를 얼마나 잘 찾아오는지 평가했다.  
✅ 검색 품질이 낮으면 Generation 단계에서 근거 부족 답변이나 Citation 오류가 발생하기 쉽다.  
✅ 주요 결과 파일은 `rag_evaluation/results/real_retrieval_results.jsonl`과 `rag_evaluation/results/real_retrieval_summary.json`이다.  
✅ 다음 단계는 검색 결과를 입력으로 사용해 Answer Generation을 수행하는 것이다.

