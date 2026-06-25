# 07 Priority Engine Analysis

## 분석 대상

기준 출력:

```text
data/processed/ml_priority/priority_engine_scores_tuned.csv
```

기준 엔진:

```text
PREPROCESSING/osj/07_priority_engine_tuned.py
```

## 전체 분포

총 row 수:

```text
2362
```

priority level 분포:

```text
low    1732
urgent  316
high    222
medium   92
```

priority score 분포:

```text
mean 24.27
50%   7.56
75%  43.10
90%  70.50
95%  76.90
99%  78.54
max  79.07
```

해석:

```text
상위 10% 정도가 urgent 경계(70점)를 넘는다.
v1 대비 urgent 과포화는 줄었지만, 여전히 low 비중은 매우 높다.
```

## priority level을 실제로 가르는 축

### risk level x priority level

```text
urgent = critical만 존재
high   = critical + high
medium = high + 일부 medium
low    = 대부분 low, 일부 medium
```

상세:

```text
urgent:
  critical 316

high:
  critical 154
  high      68

medium:
  high      78
  medium    14

low:
  low     1593
  medium   139
```

판단:

```text
07은 사실상 risk_level_calibrated가 가장 큰 축이다.
특히 urgent는 현재 규칙상 critical risk의 운영 표현에 가깝다.
```

### leadtime x priority level

상세:

```text
urgent:
  0-24h 176
  1-3d  140

high:
  0-24h  54
  1-3d  132
  3-7d   36

medium:
  0-24h 13
  1-3d  18

low:
  0-24h 26
  1-3d  41
```

판단:

```text
leadtime은 high/urgent 분해에 기여한다.
다만 risk가 낮으면 leadtime이 짧아도 low에 남는 케이스가 존재한다.
```

## 점수 구성요소 평균

priority별 평균:

```text
risk_base_score
  urgent 38.0000
  high   34.9369
  medium 26.0217
  low     4.8828

risk_probability_component_score
  urgent 17.5551
  high   16.3032
  medium 10.4735
  low     1.1476

leadtime_component_score
  urgent 14.1025
  high    9.7405
  medium  3.5261
  low     0.4074

anomaly_component_score
  urgent 2.7426
  high   2.6135
  medium 2.5849
  low    2.5665

history_adjustment_score
  urgent 1.5949
  high   1.1892
  medium 1.2609
  low   -0.0381
```

핵심 해석:

```text
1. risk가 07 점수의 지배 항이다.
2. leadtime이 그 다음 축이다.
3. anomaly는 level 간 차이가 매우 작다.
4. history는 보조 조정값 수준이다.
```

## priority reason 패턴

상위 reason:

```text
leadtime_confidence_damped                                                  1654
risk=critical|leadtime=1-3d|history_adjusted                                 196
risk=critical|leadtime=0-24h|history_adjusted                                128
risk=high|leadtime_confidence_damped|history_adjusted                         46
risk=critical|leadtime=1-3d                                                   43
```

priority별 대표 reason:

```text
urgent:
  risk=critical|leadtime=1-3d|history_adjusted
  risk=critical|leadtime=0-24h|history_adjusted

high:
  critical + 1-3d
  critical only
  high + short leadtime

medium:
  high + confidence_damped 중심

low:
  leadtime_confidence_damped 중심
```

판단:

```text
low 대부분은 "낮은 risk + 낮거나 감쇠된 leadtime confidence" 케이스다.
즉 low는 anomaly가 낮아서가 아니라 risk/leadtime 근거가 약해서 low다.
```

## short leadtime인데 low인 케이스

건수:

```text
67
```

구성:

```text
low risk + 1-3d   29
low risk + 0-24h  26
medium risk + 1-3d 12
```

score 범위:

```text
mean 21.32
max  33.24
```

판단:

```text
현재 07은 "리드타임이 짧다"만으로 우선순위를 높이지 않는다.
반드시 risk 축이 같이 받쳐줘야 한다.
이건 보수적 운영 규칙으로는 타당하지만,
"짧은 리드타임이면 일단 올린다"는 현장 정책을 원하면 룰 수정이 필요하다.
```

## manufacturer / substation 쏠림

urgent 내부 manufacturer 분포:

```text
manufacturer 2    172
manufacturer 1    144
```

urgent 상위 substation:

```text
4     40
10    28
21    28
19    19
20    17
57    16
7     16
24    15
```

판단:

```text
한 제조사로 완전히 쏠리지는 않았다.
다만 일부 substation 집중 현상은 있으므로, 운영 투입 전 현장 상식과 대조가 필요하다.
```

## 현재 07의 장점

```text
1. risk 공식본과 leadtime 승격본을 한 테이블로 안정적으로 결합했다.
2. urgent 과포화를 v1보다 줄였다.
3. high 구간이 살아나서 triage 계층으로는 더 쓸만해졌다.
4. 점수 구성요소가 분해되어 있어 사후 감사가 가능하다.
```

## 현재 07의 한계

```text
1. 사실상 risk 중심 엔진이다.
2. anomaly component 분해력은 매우 약하다.
3. history adjustment 영향은 작다.
4. low 비중이 여전히 높다.
```

## 결론

```text
07 tuned v2는 현재 기준으로 사용 가능하다.
다만 성격은 "운영 triage score"이지 독립적인 진단 엔진이 아니다.
다음 보완 우선순위는:

1. tuned 출력에 raw history 컬럼 복구
2. short leadtime low 정책을 유지할지 검토
3. 08 handoff schema 고정
```

## 2026-06-25 추가 보완

```text
tuned 출력 CSV에 아래 근거 컬럼 복구 완료:

leadtime_prob_0-24h
leadtime_prob_1-3d
leadtime_prob_3-7d
lead_time_bucket_distance
days_since_last_fault_event
days_since_last_task_event
days_since_last_any_event
```

현재 07 tuned 출력은 handoff용 근거 컬럼까지 포함한다.
