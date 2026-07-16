# dev2-raglogic RAG 기준선 보고서

## 1. 목적

이 문서는 `dev2-raglogic` 브랜치에서 현재 RAG 검색 품질을 다시 측정하고, 이후 검색 및 재검토 로직 변경 전후를 비교할 출발점을 고정한다.

현재 데이터셋은 검수 완료본이 아닌 Draft Dataset이다. 따라서 이 결과는 내부 비교용 Reference Baseline이며 공식 성능 수치가 아니다.

## 2. 실행 기준

| 항목 | 값 |
|---|---|
| Git branch | `dev2-raglogic` |
| Git commit | `e7c01d6c0b3a2c87aa134153d41f605c759e6022` |
| Retrieval backend | `jsonl` |
| 평가 질문 | 전체 28건, 정량 평가 25건, unanswerable 제외 3건 |
| Dataset status | `draft` |
| Result level | `reference` |
| Official benchmark | `false` |

재현에 필요한 Dataset과 RAG corpus의 SHA-256은 `rag_evaluation/baselines/dev2_raglogic_e7c01d6_jsonl_reference.json`에 기록했다.

## 3. Top-5 기준 결과

| Metric | 결과 |
|---|---:|
| Recall@1 | 0.28 |
| Recall@3 | 0.36 |
| Recall@5 | 0.40 |
| Precision@5 | 0.08 |
| HitRate@5 | 0.40 |
| MRR | 0.3233 |
| nDCG@5 | 0.2905 |
| 검색 실패 | 0건 |
| 평균 검색 시간 | 15.61 ms |

25개의 answerable case 중 10개에서만 정답 chunk가 Top-5 안에 포함됐다. 검색기가 정상 실행되는 것과 정답 근거를 잘 찾는 것은 별개의 문제이며, 현재 주요 개선 대상은 검색 정확도다.

## 4. 이전 dev2-rag 결과와 비교

이전 `dev2-rag` Reference 결과와 현재 결과를 case별로 비교했다.

- 28개 case의 Top-5 chunk ID와 순서가 모두 동일했다.
- Recall@5, HitRate@5, MRR, nDCG@5가 모두 동일했다.
- 현재 RAG 코드에는 이전 기준 커밋 이후 변경이 있지만, 이 Dataset과 JSONL backend에 대한 검색 결과는 변하지 않았다.

따라서 이번 결과를 현재 브랜치의 새 Reference Baseline으로 사용할 수 있다.

## 5. 검색 범위 확대 실험

| 검색 범위 | 정답 포함 case | HitRate | Recall | 평균 검색 시간 |
|---:|---:|---:|---:|---:|
| Top-5 | 10/25 | 0.40 | 0.40 | 15.61 ms |
| Top-10 | 13/25 | 0.52 | 0.52 | 17.29 ms |
| Top-20 | 17/25 | 0.68 | 0.64 | 18.39 ms |

Top-10 확대 시 `retrieval_eval_002`, `retrieval_eval_003`, `retrieval_eval_013`에서 정답 chunk를 추가로 찾았다.

Top-20 확대 시 `retrieval_eval_006`, `retrieval_eval_007`, `retrieval_eval_010`, `retrieval_eval_012`에서 정답 chunk를 추가로 찾았다.

`priority_reason` category는 Top-5에서 0/3이었지만 Top-10에서 1/3, Top-20에서 2/3으로 개선됐다. 기준 미달 시 검색 범위를 단계적으로 확대하는 방향은 실험 결과로 뒷받침된다.

다만 Top-20 결과를 그대로 생성 모델에 전달하면 관련 없는 문서와 토큰이 함께 늘어난다. 확대 검색은 후보군 확보에 사용하고, 답변 생성 전에는 reranking 또는 근거 선별 단계가 필요하다.

## 6. 여전히 검색하지 못한 Case

Top-20에서도 정답 chunk를 찾지 못한 case는 다음 8건이다.

- `retrieval_eval_005`
- `retrieval_eval_008`
- `retrieval_eval_011`
- `retrieval_eval_014`
- `retrieval_eval_016`
- `retrieval_eval_017`
- `retrieval_eval_019`
- `retrieval_eval_024`

이 case들은 단순 Top-K 확대만으로 해결되지 않는다. Query 확장, semantic embedding, hybrid search, metadata filter 또는 reranker 개선 대상으로 분리해야 한다.

## 7. 답변 평가 결과 재사용 판단

현재 Top-5 결과와 기존 `answer_eval.draft.jsonl`을 비교한 결과는 다음과 같다.

- retrieved chunk ID 불일치: 0건
- retrieved context 본문 불일치: 0건
- Answer Generation dry-run 입력 경고: 0건

기존 Answer Generation 및 LLM Judge 결과는 현재 Top-5 입력과 동일한 입력에서 생성됐으므로 Reference 비교 자료로 재사용할 수 있다. 동일 입력에 대한 API 재호출은 수행하지 않았다.

다만 기존 결과는 Draft Dataset을 사용했고 생성 모델과 Judge 모델이 동일하므로 공식 Benchmark 또는 최종 승인 자료로 사용해서는 안 된다.

## 8. 다음 구현에 적용할 기준

1. 최초 검색은 Top-5로 실행한다.
2. 품질이 기준 미달이면 Top-10으로 확대한다.
3. 여전히 부족하면 최대 Top-20까지 확대한다.
4. 확대 결과는 reranking 또는 근거 선별 후 답변 생성에 전달한다.
5. Offline benchmark에서는 Recall@5 0.40, MRR 0.3233보다 낮아지면 회귀로 본다.
6. 운영 중에는 정답 label이 없으므로 Recall을 직접 사용할 수 없다. JSONL Reference 결과에서 `top score >= 6`, `unique matched terms >= 2`를 Draft runtime proxy로 보정했다.
7. 이 proxy의 Reference 분류 성능은 Precision 0.75, Recall 0.90, F1 약 0.82이며 운영 승인 기준은 아니다.
8. `insufficient_evidence` targeted rerun은 Top-10부터 시작하고 품질이 계속 미달이면 Top-20까지 확대한다.
9. 별도 모델 기반 semantic reranker는 아직 없으며, 확대 결과에는 결정적 운영 신호 reranker를 적용한다.

## 9. 결론

현재 JSONL RAG의 Top-5 검색 기준선은 Recall@5 0.40이다. Top-K 확대는 Recall을 최대 0.64까지 높이지만, Top-20에서도 해결되지 않는 질문이 8건 남는다.

따라서 재검토 로직은 단순히 검색 개수만 늘리는 방식이 아니라 `Top-5 검색 -> 품질 판정 -> Top-10/20 확대 -> 재정렬 -> 최종 근거 선별` 구조로 구현하는 것이 적절하다.

## 10. 후속 구현 상태

기준선 측정 후 다음 백엔드 로직을 추가했다.

- Answer Judge가 `retrieval_insufficient=true`로 판정한 경우에만 자동 검색 확대를 실행한다.
- 자동 확대는 최대 Top-20 후보를 한 번 조회한다.
- 후보는 원 검색 순위, 운영 입력의 고장·설비 신호, 문서 역할, 출처 신뢰도를 사용한 `deterministic_operational_v1` 방식으로 재정렬한다.
- 재정렬 결과 중 상위 5개만 재생성 답변의 근거로 전달한다.
- 답변 생성과 Judge는 최초 및 재생성 후보마다 각각 한 번으로 제한한다.
- 확대 검색 실패 시 기존 Top-5 근거로 재생성하고 사람 검토 경로를 유지한다.

로컬 pgvector 100건 검증에서는 검색 오류가 없었고, 43건에서 기존 Top-5 밖 후보가 재정렬 후 최종 5개 안으로 이동했다. 이 수치는 reranker의 동작 검증 결과이며 관련성 정답률 개선을 의미하는 공식 성능 지표는 아니다.
