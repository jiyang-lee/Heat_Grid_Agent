# Model Comparison Guide

이 문서는 다른 사람의 전처리부터 우선순위 로직까지의 모델과 현재 `best` 파이프라인을 비교할 때 사용할 기준이다.

비교 목적은 승패를 단순히 가르는 것이 아니라, 상대 모델의 장점 중 현재 파이프라인에 가져올 만한 것을 찾는 것이다.

## 비교 입력을 맞추는 기준

먼저 아래 조건을 맞춘 뒤 비교한다.

```text
동일 설비 범위
동일 시간 범위
동일 event/fault 정의
동일 train/validation/holdout split
동일 pseudo-clean 정의
동일 lead-time window 정의
```

현재 best의 key는 다음이다.

```text
manufacturer
substation_id
window_start
window_end
```

다른 모델의 산출물도 이 key로 merge할 수 있어야 한다.

## 1. 전처리 비교

확인할 항목:

```text
timestamp 정렬 방식
station/manufacturer/configuration 연결 방식
결측 처리 방식
상수 column 제거 여부
결측률 높은 column 제거 기준
categorical encoding 방식
시간 feature 생성 방식
미래 정보 leakage 방지 여부
train/validation/holdout split 방식
event 직전 구간 제외 방식
```

현재 best의 강점:

```text
6시간 trainable window가 이미 정리되어 있음
feature contract와 imputation value가 분리되어 있음
event history feature는 risk/leadtime 학습 입력에서 기본 제외
lag/rolling은 station causal segment 기준으로 계산
```

가져올 만한 상대 모델 장점:

```text
더 명확한 결측 처리 정책
설비 타입별 feature normalization
계절/외기온 보정이 더 안정적인 방식
센서 단위 quality flag가 더 잘 정의된 방식
```

## 2. anomaly score 비교

현재 best:

```text
6h engineered feature:
Mahalanobis + IsolationForest

multi-window:
1h/3h/6h/12h anomaly confirmation

raw AE:
AutoEncoder residual -> Mahalanobis -> q999/q998 criticality
```

비교할 항목:

```text
anomaly score가 무엇을 의미하는가
score threshold가 fixed인지 quantile인지 validation 기반인지
criticality/persistence/debounce가 있는지
window length와 stride는 무엇인지
raw point 기반인지 engineered window 기반인지
설비군별 normal distribution을 따로 쓰는지
```

현재 best에서 유지할 점:

```text
anomaly score를 고장 확률로 해석하지 않음
6h main anomaly와 raw AE 확증 신호를 분리
1h/3h/6h/12h를 역할별로 분리
24h anomaly는 false positive가 높아 운영 feature에서 제외
```

상대 모델에서 가져올 만한 점:

```text
더 안정적인 threshold calibration
설비군별 threshold를 false positive guard와 함께 쓰는 방식
rolling replay가 더 실제 운영에 가까운 방식
feature contribution이 더 설비적으로 납득되는 방식
```

## 3. risk 모델 비교

현재 best:

```text
LightGBM binary classifier
target = label == pre_fault
학습 feature 수 = 313
risk_probability = 모델 원 확률
risk_score = temporal smoothing 적용 운영 점수
```

현재 risk_score:

```text
risk_score = max(
  risk_probability_raw,
  0.90 * trailing 24h max,
  1.05 * trailing 48h mean
)
```

비교할 항목:

```text
target 정의가 normal vs pre_fault인지
pre_fault horizon이 몇 일인지
event label leakage가 없는지
class imbalance 처리 방식
threshold 선택 방식
false positive guard가 있는지
설비군별 threshold override가 있는지
temporal smoothing이 causal인지
```

현재 best에서 유지할 점:

```text
raw AE와 multi-window anomaly를 risk 모델 입력에서 기본 제외
event-level validation threshold selector 사용
row metric과 event metric을 분리
false positive episode를 같이 평가
```

상대 모델에서 가져올 만한 점:

```text
calibration이 더 좋은 risk probability
설비군별 threshold가 false positive를 낮추는 방식
pre_fault 정의가 더 현장 이벤트와 맞는 방식
```

## 4. leadtime 모델 비교

현재 best:

```text
LightGBM multiclass
class = 0-24h / 1-3d / 3-7d
feature 수 = 454
leadtime은 priority 참고 신호
```

비교할 항목:

```text
leadtime을 직접 예측하는지 사후 평가하는지
bucket 정의가 무엇인지
pre_fault row만 학습하는지
정상 row에 대한 leadtime 출력을 어떻게 해석하는지
top1/top2 accuracy와 bucket distance를 같이 보는지
```

현재 best에서 유지할 점:

```text
leadtime을 최종 판단값으로 쓰지 않고 참고 신호로 제한
risk horizon/episode feature를 leadtime 학습 입력에서 제외
leadtime bucket 점수는 priority에서 0.75 scale로 제한
```

상대 모델에서 가져올 만한 점:

```text
bucket calibration이 더 안정적인 방식
leadtime confidence를 priority에 더 잘 반영하는 방식
near-term probability 정의가 더 명확한 방식
```

## 5. priority 로직 비교

현재 best:

```text
rule-based priority engine
priority_score 0-100
priority_level = urgent / high / medium / low
```

현재 priority 구성:

```text
risk_base_score
risk_probability_component_score
leadtime_component_score
leadtime_ordinal_component_score
anomaly_component_score
multi_window_anomaly_component_score
risk_episode_component_score
multi_horizon_component_score
history_adjustment_score
urgency_bonus_score
```

비교할 항목:

```text
priority가 ML 모델인지 rule인지
각 component가 설명 가능한지
false positive를 낮추는 억제 로직이 있는지
최근 정비/작업 이벤트를 감점하는지
raw AE 같은 확증 신호를 어떻게 반영하는지
Top-K ranking 품질을 보는지
```

현재 best에서 유지할 점:

```text
priority를 rule-based로 유지해 설명 가능성 확보
risk 중심, leadtime은 보조 신호
raw AE와 multi-window confirmation을 확증/가산점으로 사용
priority_reason으로 근거를 남김
```

상대 모델에서 가져올 만한 점:

```text
우선순위 점수 calibration이 더 안정적인 방식
현장 작업량을 고려한 Top-K 제한 방식
원인 feature를 priority reason에 더 잘 연결하는 방식
```

## 6. 평가 지표 비교

현재 best에서 반드시 보는 지표:

```text
row precision / recall / F1
ROC-AUC
average precision
event_recall
event_recall_24h / 3d / 7d
median_first_alarm_lead_hours
normal_false_row_rate
clean_false_row_rate
false_positive_episodes
false_episodes_per_site_month
precision_at_k
event_recall_at_k
urgent_recall_at_k
NDCG@K
```

단순 정확도만 비교하면 안 된다. 이 프로젝트는 정상 row가 많고, 실제 목적은 신고/정비 이벤트 전에 위험한 설비를 먼저 찾는 것이므로 event recall, false alarm, Top-K ranking 품질이 중요하다.

## 7. 비교용 산출물 형식

다른 모델도 가능하면 아래 CSV를 만들어 비교한다.

```text
other_model_scores.csv
```

필수 column:

```text
manufacturer
substation_id
window_start
window_end
label
fault_event_id
estimated_lead_time_hours
other_anomaly_score
other_anomaly_label
other_risk_score
other_priority_score
other_priority_level
```

있으면 좋은 column:

```text
other_leadtime_bucket
other_leadtime_confidence
other_alarm_reason
other_feature_contribution_top1
other_feature_contribution_top2
other_feature_contribution_top3
```

## 8. 최종 비교 결론 양식

비교 결과는 아래 형식으로 정리한다.

```text
1. 상대 모델에서 가져올 점
2. 현재 best에서 유지할 점
3. 현재 best에서 버릴 점 또는 약화할 점
4. 추가 실험이 필요한 점
5. 운영 기준에 바로 반영할 수 있는 점
6. 반영하면 위험한 점
```

결론을 낼 때는 반드시 성능 숫자와 운영 해석을 같이 적는다.

예시:

```text
상대 모델의 3시간 rolling threshold는 holdout event recall을 0.90에서 0.95로 올렸지만,
normal false row rate도 0.03에서 0.12로 증가했다.
따라서 기본 알람으로는 부적합하고, priority 보조 feature로만 실험한다.
```
