# DA reference 파이프라인과 best 파이프라인 비교

## 결론 요약

현재 `best`의 anomaly score는 raw point가 아니라 `trainable_windows.csv`의 6시간 window feature를 기준으로 만든다.
DA reference는 raw point-level sensor를 Conditional AutoEncoder로 복원하고, residual을 Mahalanobis distance로 score화한 뒤 5일 rolling window에서 alarm을 평가한다.

따라서 두 시스템은 모두 “정상 기준에서 벗어난 정도를 score로 만들고 persistence를 둔다”는 점은 같지만, score 단위와 alarm 정책이 다르다.

## 공통점

- 둘 다 정상 기준 분포에서 벗어난 정도를 anomaly score로 만든다.
- 둘 다 train-normal 기준 threshold를 사용한다.
- 둘 다 일시적인 튐을 줄이기 위해 criticality/persistence 개념을 둔다.
- 둘 다 anomaly score를 최종 의사결정에 직접 쓰지 않고 후속 판단 단계에 연결한다.
- 둘 다 false alarm 통제가 핵심 운영 기준이다.

## 차이점

| 항목 | DA reference | 현재 `best` |
|---|---|---|
| score 단위 | raw sensor point-level | 6시간 window feature row |
| score 생성 | Conditional Dense AE reconstruction residual -> Mahalanobis distance | IsolationForest score + LedoitWolf Mahalanobis distance |
| Mahalanobis 대상 | AE residual 벡터 | scaled window feature 벡터 |
| threshold | train score q999, q998 | anomaly는 train-normal q99, risk는 validation F0.5 기반 threshold |
| criticality | 5일 rolling window 안에서 score > threshold면 +1, 아니면 -1 | station별 시간순으로 ensemble score ratio >= 1이면 +1, 아니면 -1 |
| criticality threshold | 추천 rule `q999_c32` | 기본 `criticality >= 5` |
| rolling window | 5일 window, 1일 stride | upstream 6시간 window, 별도 5일 rolling alarm 없음 |
| alarm 정책 | `q999_c32`를 운영 default로 추천 | priority rule에서 risk, leadtime, anomaly criticality를 점수화 |
| lead time | first alarm time과 report time 차이를 사후 계산 | leadtime bucket을 모델이 직접 예측 |
| 평가 지표 | fault recall, covered recall, false periods/site-month, median lead days | anomaly/risk precision/recall/F1/AUC, leadtime accuracy/top2, priority 분포 |

## 현재 best의 anomaly score 방식

현재 anomaly score는 window 기반이다.

- 입력: `data/processed/ml_features/trainable_windows.csv`
- window 길이: 전체 행이 6시간 duration
- 일반 stride: 대부분 6시간 간격
- score:
  - `iforest_anomaly_score`
  - `mahalanobis_score`
  - `iforest_score_ratio`
  - `mahalanobis_score_ratio`
  - `anomaly_ensemble_score`

현재 `anomaly_ensemble_score`는 아래 의미다.

```text
0.47 * iforest_score_ratio
+ 0.53 * mahalanobis_score_ratio
```

`score_ratio >= 1`은 해당 모델의 threshold를 넘었다는 뜻이다.

## Criticality 사용 현황

현재 `best`에도 criticality가 있다.

```text
if anomaly_ensemble_score >= 1:
    criticality += 1
else:
    criticality = max(0, criticality - 1)
```

그리고 아래 피쳐로 저장된다.

```text
anomaly_criticality
anomaly_event_label
```

이 값은 이미 risk와 priority에 들어간다.

- risk 모델 feature: `anomaly_criticality`, `anomaly_event_label`
- priority component: `anomaly_component_score`
- priority bonus: high risk + near leadtime + criticality 조건

다만 현재 criticality는 레퍼런스보다 약하다.

- 레퍼런스: 5일 rolling 안에서 c32
- 현재: 6시간 window 흐름에서 c5

현재 c5는 대략 6시간 window 기준 약 30시간 persistence에 해당한다.
레퍼런스 c32는 point-level sampling 간격에 따라 다르지만 훨씬 강한 debounce 정책이다.

## 여기 프로젝트에서 가져올 만한 방식

1. `q999_c32` 같은 alarm rule grid를 추가한다.

현재 `best`는 anomaly 자체의 운영 alarm rule을 충분히 sweep하지 않는다.
다음처럼 실험해야 한다.

```text
threshold: q99, q995, q998, q999
criticality: 4, 8, 12, 16, 24, 32
window: 3d, 5d, 7d
```

2. first alarm lead time을 사후 평가 지표로 추가한다.

현재 leadtime은 모델 출력이다.
하지만 운영 관점에서는 별도로 아래 지표가 필요하다.

```text
fault_report_time - first_alarm_time
```

3. false alarm을 period/site-month 기준으로 본다.

현재는 row 단위 false positive rate가 중심이다.
운영 알람은 row가 아니라 “알람 에피소드”가 중요하므로 아래 지표를 추가해야 한다.

```text
official normal false period rate
clean false periods per site-month
false alarm episodes per site-month
alarm window rate
```

4. covered recall을 추가한다.

모델이 skip한 구간이나 feature 부족 구간이 있으면 total recall만으로는 판단이 흐려진다.

```text
fault_recall_total
fault_recall_covered
skipped_fault_count
```

5. criticality를 priority에서 더 강한 독립 근거로 둔다.

현재는 priority에서 criticality 점수가 최대 3점이고 bonus 조건에도 일부만 들어간다.
레퍼런스식 persistence를 반영하려면 아래 같은 별도 피쳐가 낫다.

```text
criticality_ratio = anomaly_criticality / criticality_threshold
rolling_cmax_5d
first_alarm_time
alarm_episode_count_30d
```

## 현재 프로젝트에서 유지해야 할 방식

1. risk 모델은 유지한다.

레퍼런스는 anomaly alarm 중심이고, 현재 프로젝트는 risk 모델이 `normal vs pre_fault`를 학습한다.
이건 anomaly만으로 고장 전조를 판단하는 것보다 운영 우선순위에 더 적합하다.

2. leadtime bucket 모델은 유지한다.

레퍼런스의 lead time은 사후 평가 지표이고, 현재 프로젝트는 별도 leadtime 모델을 갖고 있다.
둘은 대체 관계가 아니라 병행해야 한다.

```text
leadtime model = 앞으로 얼마나 임박했는지 예측
alarm lead time = 실제 alarm이 얼마나 일찍 울렸는지 평가
```

3. priority rule engine은 유지한다.

최종 운영 우선순위는 모델 하나보다 다음 조합이 더 설명 가능하다.

```text
risk probability
leadtime bucket
anomaly consensus
criticality
recent event history
```

## 위험한 차이 또는 개선 필요점

1. 현재 anomaly는 AE residual 기반이 아니다.

레퍼런스:

```text
AE residual -> Mahalanobis
```

현재:

```text
scaled window feature -> Mahalanobis
IsolationForest score -> ensemble
```

따라서 논문식 residual anomaly와 완전히 같은 의미는 아니다.

2. 현재 threshold가 q999보다 낮다.

현재 anomaly threshold는 q99다.
민감도는 높을 수 있지만 운영 alarm으로 바로 쓰기에는 false alarm이 늘 수 있다.

3. 현재 c5는 운영 debounce로는 약할 수 있다.

6시간 window 기준 c5는 약 30시간 persistence다.
레퍼런스 `q999_c32` 수준의 low-noise alarm 정책과는 강도가 다르다.

4. 현재 평가는 row-level 성격이 강하다.

운영에서는 6시간 row 하나가 아니라 “며칠 동안 같은 설비에 알람이 이어졌는가”가 중요하다.
episode collapse가 필요하다.

5. M1/M2 라벨 신뢰도 문제가 현재 프로젝트에도 있다.

레퍼런스는 M1만 대상으로 삼고 M2를 제외했다.
현재 프로젝트는 manufacturer 1/2를 함께 쓰며, 특히 manufacturer 2 SH는 별도 threshold override가 있을 정도로 동작이 다르다.

## 다음 실험 우선순위

1. `best`에 alarm replay 평가를 추가한다.

```text
input: best/output/anomaly_scores.csv
rules: q99/q995/q998/q999 x c5/c8/c12/c16/c24/c32
window: 5d rolling, 1d stride
output: alarm_replay_metrics.csv
```

2. priority에 rolling persistence feature를 추가한다.

```text
rolling_cmax_5d
criticality_ratio
alarm_event_label_q999_c32
first_alarm_time
```

3. leadtime을 두 종류로 분리한다.

```text
predicted_leadtime_bucket: 모델 예측
observed_alarm_lead_days: first alarm 기반 사후 평가
```

4. M1/M2를 분리 평가한다.

```text
manufacturer 1 전체
manufacturer 2 전체
manufacturer 2 SH
manufacturer 2 non-SH
```

5. false alarm 지표를 운영형으로 바꾼다.

```text
false row rate
false period rate
false episode rate
false episodes per site-month
clean alarm window rate
```

## 최종 판단

레퍼런스에서 가장 가져와야 할 것은 모델 구조 자체보다 alarm replay 방식이다.

현재 `best`는 risk/leadtime/priority 구조가 더 풍부하다.
하지만 alarm 정책은 레퍼런스가 더 운영 친화적이다.

따라서 추천 방향은 다음이다.

```text
현재 best 유지:
Mahalanobis + IsolationForest -> risk -> leadtime -> priority

레퍼런스에서 추가:
q999 계열 threshold
5일 rolling alarm replay
c32 같은 persistence grid
first alarm lead days
false episode/site-month 평가
```
