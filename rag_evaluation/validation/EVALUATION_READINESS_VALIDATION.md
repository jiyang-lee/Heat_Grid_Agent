# Evaluation Readiness Validation

검증 대상: `rag_evaluation/review/retrieval_eval.review.jsonl`  
검증 방식: 서버, Docker, DB, Retrieval Engine 실행 없이 정적 JSONL 필드만 확인했다.  
검증 목적: Retrieval Evaluation Engine 구현 전에 현재 review dataset으로 Recall@K, Precision@K, MRR, nDCG@K 등을 계산할 수 있는지 판단한다.

## 1. Dataset 상태 요약

| 항목 | 값 |
|---|---:|
| 전체 case 수 | 28 |
| `answerable=true` | 25 |
| `answerable=false` | 3 |
| `label_status=draft` | 28 |
| `review_required=true` | 28 |
| relevant label 보유 case | 25 |
| relevant label 없는 case | 3 |
| total `relevant_chunk_ids` | 30 |
| total `partially_relevant_chunk_ids` | 40 |
| answerable인데 relevant label이 없는 case | 0 |
| unanswerable인데 relevant label이 있는 case | 0 |

정적 구조상 Evaluation Engine 입력으로 필요한 주요 필드(`case_id`, `query`, `answerable`, `relevant_chunk_ids`, `partially_relevant_chunk_ids`, `label_status`, `review_required`)는 존재한다.

## 2. 현재 review dataset을 그대로 Evaluation Engine 입력으로 사용할 수 있는가?

**YES, 단 reference/draft 평가용으로만 가능하다.**

현재 JSONL은 Evaluation Engine이 query를 읽고, 검색 결과의 chunk id 목록과 `relevant_chunk_ids`를 비교해 Recall@K, Precision@K, MRR을 계산하는 데 필요한 최소 구조를 갖고 있다.

하지만 모든 case가 `label_status=draft`이고 `review_required=true`다. 따라서 결과는 공식 성능 수치가 아니라 Evaluation Engine 개발, 파이프라인 검증, metric 계산 smoke test, draft benchmark 용도로만 사용해야 한다.

## 3. `review_required=true`여도 평가가 가능한가?

**계산은 가능하지만, 공식 해석은 불가능하다.**

`review_required=true`는 label이 사람이 최종 승인한 ground truth가 아니라는 뜻이다. Engine은 이 값을 보고도 계산을 수행할 수 있지만, 최종 리포트에서는 다음을 명시해야 한다.

- 라벨은 draft 상태다.
- 사람이 relevant/partial/confusable을 최종 확정하지 않았다.
- 성능 수치는 모델 품질의 공식 지표가 아니라 라벨 설계 검증용 참고값이다.
- 낮은 점수가 검색 품질 문제인지 라벨 미확정 문제인지 분리되지 않는다.

권장 구현은 `--allow-draft-labels` 또는 `evaluation_level=reference` 같은 명시 옵션이 있을 때만 draft dataset 평가를 허용하는 것이다.

## 4. `label_status=draft`가 Recall 계산에 주는 영향

Recall@K 수식 자체는 계산 가능하다.

```text
Recall@K = top K 검색 결과에 포함된 relevant_chunk_ids 수 / 전체 relevant_chunk_ids 수
```

다만 `label_status=draft`에서는 분모인 `relevant_chunk_ids`가 최종 gold label이라고 보장되지 않는다. 따라서 다음 왜곡이 가능하다.

- 실제 relevant chunk가 label에 빠져 있으면 Recall이 과소평가된다.
- partial로 둔 chunk가 실제로 relevant라면 Recall이 과소평가된다.
- 현재 relevant로 둔 chunk가 partial에 가깝다면 Recall이 과대평가된다.
- unanswerable case 처리 정책이 명확하지 않으면 macro 평균이 흔들릴 수 있다.

결론적으로 draft label의 Recall은 **계산 가능한 draft recall**이지 **공식 recall**이 아니다.

## 5. Relevant Chunk Label만으로 Recall 계산이 가능한가?

**YES.**

`relevant_chunk_ids`만 있으면 다음 Retrieval metric은 계산 가능하다.

- Recall@K
- Precision@K
- MRR
- Hit@K
- no-hit rate

단, `answerable=false`이고 `relevant_chunk_ids=[]`인 case는 일반 Recall/Precision/MRR 평균에서 제외하거나 no-answer retrieval 분석으로 별도 집계하는 것이 안전하다.

## 6. Partially Relevant Chunk는 nDCG 계산에 사용할 수 있는가?

**일부 가능하다.**

현재 dataset에는 `partially_relevant_chunk_ids`가 있으므로 단순 gain을 정의하면 nDCG@K 계산이 가능하다.

권장 draft gain:

| candidate | gain |
|---|---:|
| `relevant_chunk_ids` | 2 |
| `partially_relevant_chunk_ids` | 1 |
| 그 외 | 0 |

하지만 현재 dataset에는 chunk별 graded relevance score가 별도 필드로 존재하지 않는다. 따라서 nDCG@K는 세밀한 graded relevance가 아니라 **relevant=2, partial=1 기반의 coarse nDCG**로만 계산해야 한다.

공식 nDCG를 원하면 사람이 각 chunk별 relevance grade를 확정해야 한다.

## 7. 자동 평가 가능 Metric과 어려운 Metric

| Metric | 현재 Dataset으로 자동 평가 | 조건/한계 |
|---|---|---|
| Recall@K | 가능 | `answerable=true` 및 `relevant_chunk_ids` 보유 case 기준. draft label 한계 명시 필요 |
| Precision@K | 가능 | 검색 결과 top K와 relevant label 비교 가능. partial 처리 정책 필요 |
| MRR | 가능 | 첫 relevant chunk rank 계산 가능 |
| Hit@K | 가능 | top K에 relevant chunk가 하나라도 있는지 계산 가능 |
| nDCG@K | 일부 가능 | relevant=2, partial=1 coarse gain으로 가능. 공식 graded nDCG는 아님 |
| no-answer retrieval accuracy | 일부 가능 | `answerable=false` case 3건만 있어 표본이 작음 |
| hard negative hit rate | 가능 | `irrelevant_but_confusable_chunk_ids`를 사용하면 가능 |
| backend 비교(pgvector/JSONL) | Engine 구현 후 가능 | 동일 query를 backend별로 실행해야 함 |
| latency | 어려움 | dataset에는 timestamp가 없음 |
| Grounding | 어려움 | 최종 LLM 답변과 retrieval context가 필요 |
| Faithfulness | 어려움 | 최종 답변 claim과 source alignment가 필요 |
| Hallucination | 어려움 | 답변 생성 결과와 judge/human label 필요 |
| Citation Accuracy | 어려움 | 답변 내 citation과 supporting chunk alignment 필요 |

## 8. 현재 Dataset만으로 Ground Truth 역할을 수행할 수 있는가?

**부분적으로만 가능하다.**

현재 review dataset은 Retrieval Engine 개발과 metric 계산 검증을 위한 **draft ground truth** 역할은 수행할 수 있다. 하지만 사람이 승인한 official gold dataset은 아니다.

Ground Truth 수준 구분:

| 수준 | 현재 해당 여부 | 설명 |
|---|---|---|
| Reference | 가능 | Engine 구현, metric 계산, 결과 포맷 검증용 |
| Draft | 가능 | 초안 benchmark로 비교 실험 가능. 한계 명시 필수 |
| Official | 불가 | `review_required=true`, `label_status=draft`이므로 공식 성능 발표에는 부적합 |

## 9. review dataset으로 평가할 경우 Report에 명시해야 할 한계

최종 report에는 다음 문구를 반드시 포함해야 한다.

- 본 평가는 `label_status=draft` dataset 기반이다.
- 모든 case가 `review_required=true`이므로 도메인 전문가 승인 전 수치다.
- `relevant_chunk_ids`는 검수 전 후보 label이며 official gold label이 아니다.
- `partially_relevant_chunk_ids`는 coarse nDCG 또는 오류 분석용으로만 사용했다.
- `answerable=false` case는 일반 Recall/Precision/MRR 평균에서 제외하거나 별도 no-answer 분석으로 집계했다.
- 점수 저하는 retrieval 품질 문제와 label draft 문제를 분리하지 못할 수 있다.
- 현재 metric은 chunk id 매칭 기반이며, answer grounding/faithfulness/hallucination 품질을 평가하지 않는다.
- pgvector/JSONL backend 비교, latency, token usage는 별도 실행 로그와 계측이 필요하다.

## 10. Approved Dataset이 반드시 필요한 Metric

엄밀히 말하면 Recall@K, Precision@K, MRR도 draft label로 계산은 가능하다. 하지만 **공식 성능 지표로 보고하려면 모든 retrieval metric에 approved dataset이 필요하다.**

특히 approved label이 반드시 필요한 항목:

- Official Recall@K
- Official Precision@K
- Official MRR
- Official nDCG@K
- backend 비교의 공식 승패 판단
- top_k 비교의 공식 최적값 선정
- embedding 방식 비교의 공식 품질 판단

추가로 다음 Answer 평가 계열은 현재 dataset만으로는 부족하며, approved retrieval label 외에도 최종 답변/근거 alignment label이 필요하다.

- Grounding
- Faithfulness
- Hallucination
- Citation Accuracy
- Answer Relevance

## 11. Evaluation Engine 구현 전 권장 정책

Engine은 바로 구현해도 된다. 다만 다음 안전장치를 권장한다.

1. `label_status=draft`를 허용할지 명시 옵션으로 제어한다.
2. 기본 report title에 `Draft Retrieval Evaluation` 또는 `Reference Evaluation`을 표시한다.
3. `answerable=false` case는 기본 ranking metric에서 제외하고 별도 section에 표시한다.
4. nDCG gain 정책을 report에 출력한다. 예: `relevant=2`, `partial=1`.
5. `review_required=true` case 수를 report summary에 반드시 출력한다.
6. `approved_only=true` 모드에서는 현재 dataset으로 실행 시 평가를 중단하도록 한다.

## 12. 최종 답변

### ① Review Dataset으로 Evaluation Engine을 실행해도 되는가?

**YES.**

단, 공식 성능 평가가 아니라 Reference/Draft 평가로만 실행해야 한다.

### ② YES라면 최종 결과는 Reference, Draft, Official 중 어떤 수준인가?

**Draft에 가까운 Reference 결과다.**

Engine 구현과 metric 산출 검증에는 사용할 수 있지만, 도메인 검수 전이므로 Official 결과가 아니다.

### ③ Approved Dataset이 반드시 필요한 Metric은 무엇인가?

공식 보고 기준으로는 다음 metric에 approved dataset이 필요하다.

- Recall@K
- Precision@K
- MRR
- nDCG@K
- backend 비교
- top_k 비교
- embedding 방식 비교

계산 자체는 draft로 가능하지만, 공식 해석에는 approved label이 필요하다.

### ④ 다음 단계에서 Evaluation Engine을 바로 구현해도 되는가?

**YES.**

단, 첫 구현 목표는 official benchmark가 아니라 draft/reference dataset 기반의 metric pipeline 구현이어야 한다. Report에는 반드시 `label_status=draft`, `review_required=true`, `official result 아님`을 명시해야 한다.
