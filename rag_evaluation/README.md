# HeatGrid Retrieval Evaluation

이 모듈은 HeatGrid RAG의 Retrieval 성능을 정량 평가하기 위한 독립 실행 파이프라인이다. 현재 단계는 Official Benchmark가 아니라 `Draft / Reference Metric Pipeline` 구현이다.

## 범위

구현하는 지표:

- Recall@1, Recall@3, Recall@5
- Precision@1, Precision@3, Precision@5
- MRR
- nDCG@5
- HitRate@1, HitRate@3, HitRate@5

이번 단계에서 구현하지 않는 항목:

- Grounding
- Faithfulness
- Hallucination
- Citation Accuracy
- Latency
- Token Cost

## 입력 Dataset

Dataset 선택 우선순위:

1. `rag_evaluation/datasets/retrieval_eval.approved.jsonl`
2. `rag_evaluation/review/retrieval_eval.review.jsonl`

현재 repository에는 review dataset이 있으므로 결과 metadata는 다음과 같다.

```json
{
  "dataset_status": "draft",
  "result_level": "reference",
  "official_benchmark": false
}
```

Approved dataset 파일을 추가하면 같은 engine으로 official benchmark를 실행할 수 있도록 설계했다.

## 실행 방법

Python이 PATH에 있는 환경:

```powershell
python rag_evaluation/scripts/run_retrieval_eval.py
```

Codex 번들 Python을 사용하는 예:

```powershell
C:\Users\Admin\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe rag_evaluation/scripts/run_retrieval_eval.py
```

출력:

- `rag_evaluation/results/retrieval_results.jsonl`
- `rag_evaluation/results/retrieval_summary.json`

## Mock Retrieval 입력

이번 단계에서는 실제 `RagSearcher`를 호출하지 않는다. 대신 다음 형식의 JSONL을 `--mock-retrieval-file`로 넣을 수 있다.

```json
{"case_id":"retrieval_eval_001","retrieved_chunk_ids":["danfoss_troubleshooting_table__row001"]}
```

mock file이 없으면 label echo mock을 사용한다. 이는 metric pipeline smoke test 용도이며 실제 검색 품질을 의미하지 않는다.

## answerable=false 처리

`answerable=false` case는 Recall, Precision, MRR, HitRate, nDCG macro average에서 제외한다. Summary에는 `excluded_unanswerable_count`로 별도 집계한다.

## 실제 RagSearcher 연결 위치

다음 단계에서는 `run_retrieval_eval.py`의 `load_mock_retrievals()` 대신 adapter를 추가하면 된다.

권장 연결점:

- `RagSearcher.search(query=case["query"], top_k=...)`
- 또는 `InternalRagEvidenceAdapter.search(RagEvidenceRequest(...))`

Adapter 출력은 case별 `retrieved_chunk_ids` list로 변환하면 현재 metric 계산 함수를 그대로 재사용할 수 있다.

## 결과 해석 주의

현재 review dataset은 `label_status=draft`, `review_required=true`다. 따라서 결과는 Reference/Draft metric이며 official benchmark가 아니다.

Official report를 만들려면 `retrieval_eval.approved.jsonl`이 필요하다.

## 향후 확장

다음 단계 확장 후보:

- 실제 pgvector / JSONL fallback retrieval 실행
- backend 비교 report
- top_k grid 비교
- retrieval latency 계측
- Grounding / Faithfulness / Hallucination / Citation Accuracy 평가
