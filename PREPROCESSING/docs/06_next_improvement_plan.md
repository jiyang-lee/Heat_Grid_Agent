# 06 next improvement plan

## 목적

현재 06은 운영 가능한 1차 기준선은 확보했다.

하지만 상태는 아래처럼 나뉜다.

```text
risk:
  calibrated 공식본 유지

leadtime:
  timeflow promoted 후보 확보
```

따라서 다음 개선은 무작정 전체 재작성이나 파라미터 튜닝이 아니라,
먹히는 축만 좁혀서 진행해야 한다.

## 현재 기준선

### risk 공식본

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
data/processed/ml_risk/lgbm_risk_metrics_calibrated.csv
```

holdout overall:

```text
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449
roc_auc   0.7628
ap        0.6197
```

### leadtime 후보본

```text
data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv
data/processed/ml_leadtime/leadtime_bucket_metrics_promoted.csv
```

holdout:

```text
accuracy   0.6512
macro_f1   0.4405
weighted   0.6432
top2_acc   0.9651
bucket_mae 0.3837
```

## 개선 우선순위

다음 개선 순서는 아래가 맞다.

```text
1. risk false negative audit 강화
2. risk event-context 재표현
3. risk thermal relation/group feature 보강
4. leadtime timeflow 확장
5. leadtime 2버킷 urgency 보조체인 검토
6. pseudo label 재설계
```

## 1. risk false negative audit 강화

### 목적

지금까지는 false positive를 많이 봤다.
이제는 `놓친 위험구간`을 더 봐야 한다.

### 질문

```text
왜 pre_fault인데 medium/low로 남는가?
특정 manufacturer / configuration / season에 몰리는가?
특정 thermal pattern을 못 잡는가?
```

### 작업

- holdout false negative를 group별로 다시 분해
- `low`, `medium`을 따로 분리
- `0.22`, `0.44` 경계 주변 점수대 분석
- true positive와의 feature 차이 재비교

### 성공 기준

- recall을 올릴 수 있는 구체 feature 후보를 3개 이상 좁힌다.

## 2. risk event-context 재표현

### 목적

지금 event-context는 일부 bucket화가 이미 효과가 있었다.
다음은 단순 raw/bucket을 넘어서 상태형 표현으로 가야 한다.

### 후보

```text
days_since_last_fault_event
days_since_last_task_event
days_since_last_any_event
```

### 실험 방향

- `<=7d / 8-30d / 31-90d / >90d` 상태형 유지
- `has_previous_*`와 분리
- `recent_event_flag + distance_bucket` 조합 비교
- recent fault/task/any를 각각 독립 표현

### 성공 기준

- holdout overall F1 또는 recall이 공식본보다 개선
- FPR은 크게 악화되지 않을 것

## 3. risk thermal relation/group feature 보강

### 목적

절대 온도값보다 관계형 표현이 더 잘 먹히는 그룹이 이미 보였다.

### 후보 feature

```text
supply - return
storage - supply
setpoint gap
outdoor normalized gap
group z-score
```

### 실험 방향

- raw 유지 vs relation 대체
- relation + z-score 동시 사용
- group별 효과 분리 평가
- false negative 쪽에 특히 먹히는지 확인

### 성공 기준

- overall holdout과 문제 그룹 holdout을 동시에 보되
- 최소한 공식본보다 한쪽만 좋아지고 전체가 무너지면 승격 보류

## 4. leadtime timeflow 확장

### 현재 상태

```text
timeflow_lag_delta_roll3
```

가 baseline보다 소폭 개선됐다.

### 다음 후보

- slope
- rolling std
- 최근 2~4개 window 누적 변화량
- anomaly_score 증가 속도
- risk_probability 증가 속도
- thermal gap 확대 속도

### 성공 기준

- holdout macro F1을 `0.4405`보다 넘길 것

## 5. leadtime 2버킷 urgency 보조체인

### 목적

3버킷 메인 체인은 유지하되,
실무용 즉시성 판단은 더 단순한 체인이 유리할 수 있다.

### 구조

```text
0-24h
vs
1-7d
```

### 용도

- Priority Engine에서 즉시 대응 여부 판단 보조
- Agent가 "당장 점검" 여부를 더 명확히 말하도록 지원

### 주의

- 메인 leadtime 대체용이 아니라 보조체인으로 취급

## 6. pseudo label 재설계

### 목적

가장 큰 개선 여지지만 비용도 가장 크다.

### 후보

- disturbance 직후 구간 처리 변경
- maintenance 영향 구간 별도 처리
- 신고 직전이지만 명백히 작업 영향인 구간 분리
- bucket 경계 재정의

### 주의

- 성능이 바로 좋아질 수도, 떨어질 수도 있다.
- 그래서 제일 마지막 단계가 맞다.

## 실행 순서

바로 손댈 순서는 아래로 고정한다.

```text
Step 1
  risk false negative audit 강화

Step 2
  risk event-context 상태형 재표현 실험

Step 3
  risk thermal relation/group feature 재실험

Step 4
  leadtime timeflow 확장 실험

Step 5
  leadtime 2버킷 urgency 보조체인 정리

Step 6
  pseudo label 재설계 검토
```

## 지금 시점 결론

지금 바로 07/08 연결로 가도 되지만,
06을 더 개선하려면 가장 ROI가 큰 건 여전히 `risk 쪽 false negative + feature 표현`이다.

즉,

```text
다음 06 개선의 핵심은
파라미터 튜닝이 아니라
feature 표현과 label 구조다.
```
