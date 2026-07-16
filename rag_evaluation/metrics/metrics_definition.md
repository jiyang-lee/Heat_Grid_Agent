# Retrieval Metrics Definition

이 문서는 HeatGrid RAG Retrieval Evaluation Engine이 계산하는 지표를 정의한다. 현재 단계의 결과는 `label_status=draft` review dataset 기반이므로 `Reference Metric`으로 해석한다.

## 공통 처리 규칙

- `answerable=false` case는 Recall, Precision, MRR, HitRate, nDCG macro average에서 제외한다.
- `relevant_chunk_ids`만 Recall, Precision, MRR, HitRate의 정답 label로 사용한다.
- nDCG@5는 linear gain 방식을 사용한다. `relevant_chunk_ids=2`, `partially_relevant_chunk_ids=1`, 그 외 `0`이다.
- nDCG 계산 시 `partially_relevant_chunk_ids`와 `relevant_chunk_ids`가 겹치면 relevant를 우선하고 partial gain에서는 제외한다. overlap은 warning으로 남긴다.
- 중복 retrieved chunk는 순서를 보존해 dedupe하고 warning에 기록한다.
- empty retrieval은 metric 값 0으로 계산하되 warning에 기록한다.
- draft dataset 결과는 official benchmark가 아니다.

## Recall@K

정의:

```text
Recall@K = top K에 포함된 relevant chunk 수 / 전체 relevant chunk 수
```

HeatGrid에서 사용하는 이유:

운영 질문에 필요한 핵심 근거 chunk가 검색 결과 상위 K개 안에 들어오는지 확인한다. Fault Group 기반 문서 회수 목적에 가장 직접적인 지표다.

## Precision@K

정의:

```text
Precision@K = top K에 포함된 relevant chunk 수 / K
```

HeatGrid에서 사용하는 이유:

상위 검색 결과가 얼마나 정답 근거 중심으로 구성되는지 확인한다. 작업지시서 생성에 불필요한 근거가 많이 섞이는지 보는 데 유용하다.

주의:

검색 결과가 K개보다 적더라도 분모는 항상 K를 유지한다. 예를 들어 retrieved result가 2개뿐이고 K=5이면 Precision@5의 분모는 5다.

## MRR

정의:

```text
MRR = 첫 번째 relevant chunk rank의 역수
```

예: 첫 번째 정답 chunk가 1위면 1.0, 2위면 0.5, 5위면 0.2다.

HeatGrid에서 사용하는 이유:

Agent가 제한된 top_k context를 사용할 때 가장 중요한 근거가 얼마나 앞에 배치되는지 확인한다.

## nDCG@5

정의:

```text
DCG@5 = sum(gain_i / log2(i + 1))
nDCG@5 = DCG@5 / IDCG@5
```

현재 gain은 linear gain 방식이다.

| 후보 | gain |
|---|---:|
| relevant | 2 |
| partially_relevant | 1 |
| irrelevant | 0 |

`relevant`와 `partially_relevant` label이 중복되면 해당 chunk는 relevant로만 계산하고 partial ideal gain에서는 제외한다.

HeatGrid에서 사용하는 이유:

정답 chunk뿐 아니라 보조 근거가 상위에 배치되는지도 함께 평가한다. 현재 dataset은 graded relevance가 없으므로 coarse nDCG로만 해석한다.

## HitRate@K

정의:

```text
HitRate@K = top K에 relevant chunk가 하나라도 있으면 1, 아니면 0
```

HeatGrid에서 사용하는 이유:

질문별로 최소 하나의 핵심 근거를 회수했는지 빠르게 확인한다. Recall보다 단순한 운영 관점의 성공률 지표다.

## 이번 단계에서 제외한 지표

다음 항목은 Retrieval-only 평가 범위를 벗어나므로 구현하지 않는다.

- Grounding
- Faithfulness
- Hallucination
- Citation Accuracy
- Latency
- Token Cost

이 항목들은 최종 답변, citation alignment, timestamp, token usage log가 필요하다.
