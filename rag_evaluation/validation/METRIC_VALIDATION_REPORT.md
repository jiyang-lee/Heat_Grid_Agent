# Metric Validation Report

## 1. 검증 목적

4단계에서 구현한 Retrieval Evaluation Engine의 metric 계산이 수학적으로 올바른지 검증했다. 이번 검증은 실제 RAG 검색 품질 평가가 아니라, 소형 mock case를 이용한 계산 로직 검증이다.

기존 `run_retrieval_eval.py`의 label echo mock은 pipeline smoke test였고, metric 수학 검증은 이 문서의 `metric_test_cases.json`와 `test_retrieval_metrics.py`가 담당한다.

## 2. 검증한 Metric

- Recall@1
- Recall@3
- Recall@5
- Precision@1
- Precision@3
- Precision@5
- HitRate@1
- HitRate@3
- HitRate@5
- MRR
- nDCG@5

## 3. 계산 기준

### MRR

MRR은 전체 deduped `retrieved_chunk_ids` list 기준으로 첫 번째 relevant chunk의 rank를 사용한다. 따라서 relevant chunk가 top-5 밖인 rank 6에 있어도 MRR은 `1/6`이다. top-k 제한 MRR은 이번 단계에서 구현하지 않았다.

### nDCG@5

nDCG@5는 linear gain 방식을 사용한다.

| 후보 | gain |
|---|---:|
| relevant | 2 |
| partially_relevant | 1 |
| irrelevant | 0 |

공식:

```text
DCG@5 = sum(gain_i / log2(i + 1))
nDCG@5 = DCG@5 / IDCG@5
```

`relevant_ids`와 `partial_ids`가 겹치는 경우 relevant를 우선한다. 겹친 항목은 partial gain에서 제외하고, case warning에 `overlapping_relevant_partial_labels:<chunk_id>`를 남긴다.

### Precision@K

Precision@K는 검색 결과가 K개보다 적어도 분모 K를 유지한다. 예를 들어 retrieved chunk가 2개뿐이어도 Precision@5는 `relevant hit 수 / 5`로 계산한다.

## 4. 테스트 케이스별 입력과 결과

| # | 테스트 케이스 | 핵심 입력 | 수기 예상값 요약 | 실제 결과 | 판정 |
|---:|---|---|---|---|---|
| 1 | 완전 일치 | relevant `rel_a`가 1위 | Recall@1=1, Precision@1=1, HitRate@1=1, MRR=1, nDCG@5=1 | 예상값과 일치 | PASS |
| 2 | Relevant 3위 | `rel_a`가 rank 3 | Recall@1=0, Recall@3=1, HitRate@1=0, HitRate@3=1, MRR=1/3, nDCG@5=0.5 | 예상값과 일치 | PASS |
| 3 | Relevant Top-5 밖 | `rel_a`가 rank 6 | Recall@5=0, HitRate@5=0, MRR=1/6 | 예상값과 일치 | PASS |
| 4 | Relevant 여러 개 | relevant 2개 중 1개만 top-3 | Recall@3=0.5, Precision@3=1/3, MRR=0.5 | 예상값과 일치 | PASS |
| 5 | Partially Relevant 포함 | partial rank 1, relevant rank 3 | nDCG@5=0.7601875334318685 | 예상값과 일치 | PASS |
| 6 | 검색 결과 중복 | `rel_a` 중복 검색 | 첫 순위만 인정, duplicate warning 발생 | 예상값과 일치 | PASS |
| 7 | Empty Retrieval | 검색 결과 없음 | 모든 metric=0, empty warning 발생 | 예상값과 일치 | PASS |
| 8 | Relevant Set 없음 | answerable=true, relevant label 없음 | macro 제외, metric=null, missing label warning | 예상값과 일치 | PASS |
| 9 | Unanswerable Case | answerable=false | macro 제외, exclusion_reason=answerable_false | 예상값과 일치 | PASS |
| 10 | Relevant/Partial 혼합 순위 | relevant 2개, partial 2개 mixed ranking | nDCG@5=0.826764904527197 | 예상값과 일치 | PASS |

## 5. 추가 검증 결과

| 항목 | 결과 |
|---|---|
| duplicate retrieved chunk 제거 | PASS. 순서를 보존해 첫 출현만 인정 |
| K가 retrieved list 길이보다 큰 경우 | PASS. 없는 rank는 irrelevant로 간주되어 Precision@K 분모는 K 유지 |
| K가 0 또는 음수인 경우 | PASS. Recall/Precision/HitRate 모두 0 반환 |
| 알 수 없는 chunk ID | PASS. 오류 없이 irrelevant로 처리 |
| `document_id` fallback 금지 | PASS. retrieved dict에 `document_id`만 있으면 chunk id로 인정하지 않고 error 처리 |
| relevant/partial label overlap | PASS. warning을 남기고 nDCG partial gain에서는 overlap 제외 |
| JSON 직렬화 NaN/Infinity | PASS. `json.dumps(..., allow_nan=False)` 통과 |
| macro average | PASS. excluded case를 제외한 case별 평균으로 계산 |
| category/difficulty/query_intent breakdown | PASS. 전체 평균과 독립적으로 그룹별 집계 |

## 6. 발견된 버그

### Fixture 기대값 오류

초기 테스트에서 nDCG expected value 2건이 실패했다.

- `partial_relevant_ndcg`
- `mixed_relevant_partial_ranking`

원인은 구현 버그가 아니라 fixture의 수기 기대값이 `gain/log2(rank+1)` 공식과 다르게 계산된 것이었다. Python으로 직접 DCG/IDCG를 재계산해 expected value를 수정했다.

### K <= 0 guard 명시 부족

`recall_at_k()`는 slicing 동작상 우연히 0을 반환했지만, `k <= 0`에 대한 명시 guard가 없었다. 유지보수 안전성을 위해 `recall_at_k()`에 `k <= 0 -> 0.0` 처리를 추가했다.

### document_id fallback 위험

`extract_chunk_id()`가 `document_id`를 chunk id 대체값으로 허용하면 document-level id가 chunk-level metric에 잘못 매칭될 수 있었다. 실제 RAG 연결 전 안전성을 위해 `chunk_id`와 `id`만 허용하도록 수정했다.

### relevant/partial label overlap 처리

동일 chunk가 relevant와 partial label에 동시에 들어가면 nDCG ideal gain이 부풀려질 수 있었다. relevant를 우선하고 partial set에서는 제외하며, warning을 남기도록 보완했다.

## 7. 수정한 내용

수정 파일:

- `rag_evaluation/tests/metric_test_cases.json`
- `rag_evaluation/scripts/evaluation_utils.py`

수정 내용:

- nDCG fixture expected value를 공식 기준으로 수정했다.
- `recall_at_k()`에 K가 0 또는 음수일 때 0.0을 반환하는 guard를 추가했다.
- `extract_chunk_id()`에서 `document_id` fallback을 제거했다.
- relevant/partial label overlap warning과 nDCG overlap 제외 처리를 추가했다.

기존 `src/`, `heatgrid_rag/`, `heatgrid_ops/`, `simulator/`, `tests/`, `docs/`는 수정하지 않았다.

## 8. 최종 테스트 결과

실행 명령:

```powershell
C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest rag_evaluation.tests.test_retrieval_metrics
```

결과:

```text
Ran 7 tests
OK
```

Fixture 기준:

- metric test case: 10
- PASS: 10
- FAIL: 0

## 9. 남아 있는 한계

- 현재 검증은 metric 계산 로직만 검증한다.
- 실제 `RagSearcher` 또는 `InternalRagEvidenceAdapter`는 호출하지 않았다.
- 현재 draft dataset의 실제 검색 성능을 평가하지 않았다.
- nDCG는 graded relevance가 아니라 `relevant=2`, `partial=1`의 coarse gain이다.
- MRR은 전체 retrieved list 기준이며 top-k limited MRR은 별도 metric으로 구현하지 않았다.

## 10. 실제 RAG 연결 전 최종 판단

최종 판단: **PASS**.

현재 Retrieval Metric 계산 로직은 mock validation 기준으로 실제 RAG 연결 전 사용할 수 있다. 다음 단계에서는 실제 retrieval adapter가 반환하는 chunk id ranking을 `evaluate_case()`에 주입하면 된다.
