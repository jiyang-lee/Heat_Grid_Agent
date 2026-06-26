# 07 Priority Engine

## 목적

07의 역할은 ML 결과를 운영 우선순위 점수로 바꾸는 것이다.

즉 07은 고장 확정 엔진이 아니라 다음 질문에 답하는 계층이다.

```text
지금 무엇을 먼저 점검해야 하는가
```

이 단계는 `risk + leadtime + anomaly + 최근 이벤트 이력`을 합쳐
현장 점검 우선순위를 점수화한다.

## 입력 소스

### risk 공식본

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
```

### leadtime 승격본

```text
data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv
```

## 공통 입력 컬럼

식별자:

```text
manufacturer
substation_id
window_start
window_end
```

이상징후:

```text
anomaly_score
```

위험도:

```text
risk_score
risk_probability
risk_level_calibrated
```

리드타임:

```text
predicted_lead_time_bucket
predicted_lead_time_confidence
leadtime_prob_0-24h
leadtime_prob_1-3d
leadtime_prob_3-7d
lead_time_bucket_distance
```

최근 이벤트 이력:

```text
days_since_last_fault_event
days_since_last_task_event
days_since_last_any_event
```

## 점수 구조

Priority score는 아래 네 축으로 계산한다.

```text
1. risk base score
2. leadtime urgency score
3. anomaly support score
4. history adjustment score
```

## v1 baseline

### 실행 파일

```text
PREPROCESSING/osj/archive/07_priority_engine_basic.py
```

### baseline 규칙

risk base:

```text
critical -> 55
high     -> 40
medium   -> 22
low      -> 8
```

risk probability 반영:

```text
risk_probability * 25
```

leadtime urgency:

```text
0-24h -> 25
1-3d  -> 15
3-7d  -> 5
```

confidence multiplier:

```text
>= 0.8   -> 1.0
0.6~0.8  -> 0.8
< 0.6    -> 0.6
```

anomaly support:

```text
anomaly_score * 10
```

history adjustment:

```text
days_since_last_task_event <= 7d  -> -8
days_since_last_task_event <= 30d -> -4
days_since_last_any_event  <= 7d  -> -5
days_since_last_any_event  <= 30d -> -2
days_since_last_fault_event >= 365d -> +3
```

priority level:

```text
score >= 80 -> urgent
60~79       -> high
40~59       -> medium
<40         -> low
```

### baseline 산출물

```text
data/processed/ml_priority/priority_engine_scores.csv
data/processed/ml_priority/models/priority_engine_metadata.json
```

### baseline 분포

```text
low    1697
urgent  514
high     88
medium   63
```

판단:

```text
urgent 쏠림이 크고 high/medium 구간이 너무 얇다.
운영 우선순위 계층으로 쓰기엔 중간 구간 분해력이 부족하다.
```

## v2 tuned

### 실행 파일

```text
PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py
```

### tuned 규칙

risk base:

```text
critical -> 38
high     -> 28
medium   -> 15
low      -> 4
```

risk probability 반영:

```text
risk_probability * 18
```

leadtime urgency:

```text
0-24h -> 18
1-3d  -> 10
3-7d  -> 4
```

confidence multiplier:

```text
>= 0.8   -> 1.0
0.6~0.8  -> 0.8
< 0.6    -> 0.6
```

anomaly support:

```text
anomaly_score * 6
```

history adjustment:

```text
days_since_last_task_event <= 7d  -> -8
days_since_last_task_event <= 30d -> -4
days_since_last_any_event  <= 7d  -> -5
days_since_last_any_event  <= 30d -> -2
days_since_last_fault_event >= 365d and risk in {high, critical} -> +2
```

priority level:

```text
score >= 70 -> urgent
52~69       -> high
34~51       -> medium
<34         -> low
```

### tuned 산출물

```text
data/processed/ml_priority/priority_engine_scores_tuned.csv
data/processed/ml_priority/models/priority_engine_tuned_metadata.json
```

### tuned 분포

```text
low    1732
urgent  316
high    222
medium   92
```

### score 분포 요약

v1:

```text
mean 37.87
50%  16.38
75%  62.04
max 100.00
```

v2:

```text
mean 24.27
50%   7.56
75%  43.10
max  79.07
```

판단:

```text
v2는 urgent 포화를 줄이고 high 구간을 늘렸다.
완전한 균형은 아니지만, 운영 triage용으로는 v1보다 낫다.
07의 현재 추천 출력은 tuned v2다.
```

## 출력 컬럼

```text
manufacturer
substation_id
window_start
window_end

anomaly_score
risk_score
risk_probability
risk_level_calibrated
predicted_lead_time_bucket
predicted_lead_time_confidence

risk_base_score
risk_probability_component_score
leadtime_bucket_base_score
leadtime_confidence_multiplier
leadtime_component_score
anomaly_component_score
history_adjustment_score
history_adjustment_reason

priority_score
priority_level
priority_reason
engine_version
```

## 해석 원칙

07은 진단이 아니다.

07이 하는 일:

```text
위험도 + 임박도 + 최근 이벤트 이력
```

을 결합해

```text
점검 우선순위
```

로 바꾸는 것이다.

따라서 08 Agent는 07 점수를 그대로 받아도 되지만,
최종 판단 문장과 점검 제안은 08에서 완성해야 한다.

