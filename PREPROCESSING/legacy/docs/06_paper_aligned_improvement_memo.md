# 06-P paper-aligned 개선 메모

이 문서는 현재 `06-P` baseline의 상태와, 다음 보강 우선순위를 기록한다.

기준 버전:

```text
06-P2: paper_aligned_autoencoder_v1
06-P3: severity-weighted criticality counter
06-P5: paper_aligned_agent_contract_v2
```

## 현재 상태 요약

현재 선택된 event detection 기준:

```text
point threshold:
  train_rmse_p099

criticality counter:
  increment by max(anomaly_score - 1.0, 0.25)
  decrement by 1.0 on non-anomaly
  hold on maintenance anomaly

selected_criticality_threshold:
  1.0
```

현재 성능:

```text
validation:
  event_fault_count 12
  event_normal_count 10
  TP 5 / FN 7 / FP 0 / TN 10
  precision 1.0000
  recall 0.4167
  F0.5 0.7813
  false_alarm_rate 0.0000
  avg_lead_time_hours_detected_faults 59.76

holdout:
  event_fault_count 11
  event_normal_count 11
  TP 4 / FN 7 / FP 0 / TN 11
  precision 1.0000
  recall 0.3636
  F0.5 0.7407
  false_alarm_rate 0.0000
  avg_lead_time_hours_detected_faults 31.76
```

현재 Agent 계약 출력:

```text
risk levels:
  critical 5
  high 4
  low 35

normal event high/critical:
  0
```

즉 현재 baseline은 false positive를 강하게 억제하는 방향으로 보정됐다.

## 현재 강점

1. normal false positive가 계약 출력 상단에서 제거됐다.
2. event-wise precision이 validation / holdout 모두 1.0이다.
3. `main_abnormal_features`, `feature_explanation`, `priority_reason`까지 end-to-end output이 연결됐다.
4. legacy LightGBM branch와 독립된 canonical baseline 경로가 생겼다.

## 현재 한계

### 1. recall이 낮다

```text
validation recall 0.4167
holdout recall 0.3636
```

23개 fault event 중 9개만 detected다.

즉 현재 baseline은 “놓치더라도 오탐은 줄이자” 쪽으로 치우쳐 있다.

### 2. selected_criticality_threshold가 여전히 1.0이다

severity-weighted counter로 바꾼 뒤에도 최적값이 `1.0`이다.

이는 이전 binary counter보다는 낫지만, 여전히 detection 조건이 낮은 편이다.
실제 suppression은 counter 규칙 변경에서 대부분 발생했고, threshold 자체가 separation을 만들어내는 구조는 아니다.

### 3. 고정 7일 pre-report evaluation window를 아직 보장하지 못한다

현재 `06-P3` 평가는 03번에서 만들어진 window 체인을 재사용한다.

따라서 논문처럼 모든 fault event에 대해:

```text
report 이전 고정 7일 window
```

를 정확히 맞춘 평가가 아니다.

이 문제는 단순 문서 이슈가 아니라 성능 해석 자체에 영향을 준다.

### 4. 설명 feature가 아직 완전히 운영 친화적이지 않다

메타 feature는 랭킹에서 제거했지만, 다음 같은 context feature가 상단에 뜨는 경우가 있다.

```text
outdoor_temperature__std
p_net_supply_temperature__std
setpoint variation 계열
```

운영자에게는 useful할 수 있지만, 바로 점검 항목으로 연결되기엔 해석이 거칠다.

## 다음 보강 우선순위

### 우선순위 1. 03 / 06-P1 재구성으로 evaluation window 고정

목표:

```text
fault event별 report 이전 고정 7일 평가 window 재생성
normal event별 동등 길이 평가 window 고정
```

이 작업 없이는 현재 성능을 논문 정렬 성능처럼 읽기 어렵다.

### 우선순위 2. 06-P2 threshold / anomaly calibration 보강

후보:

- `train_rmse_p099` 대신 manufacturer / configuration conditional threshold 비교
- reconstruction error 외 `rolling anomaly density` 추가
- event 내 max 대신 tail mean / top-k mean 비교

목적:

```text
false positive는 유지하면서 recall을 올리는 것
```

### 우선순위 3. 06-P3 counter 규칙 실험 분리

현재 규칙:

```text
severity-weighted increment
decrement 1.0
maintenance hold
```

다음 후보:

- decrement 0.5
- anomaly severity cap 조정
- event type별 threshold 분리
- manufacturer / configuration conditional threshold

### 우선순위 4. 06-P4 설명 계층 정제

후보:

- 센서군 우선순위 테이블 추가
- setpoint / gap / actual sensor를 묶어서 요약
- explanation template를 작업지시서 문장형으로 변환

### 우선순위 5. 06-P5 priority calibration 보강

현재는:

```text
risk_score
priority_score
```

가 규칙 기반 가중합이다.

다음 보강 후보:

- normal event penalty 추가
- manufacturer / configuration baseline 차 반영
- recent history 가중치 재조정

## 바로 다음 작업 제안

가장 합리적인 순서는 다음이다.

1. `03_preprocess_windows` / `06_paper_aligned_data_selection` 보강
2. 고정 7일 pre-report event evaluation 재생성
3. `06-P2 ~ 06-P5` 재실행
4. 그 후에 `07`, `08` export 계층 고정

지금 바로 07/08로 넘어가는 것도 가능하지만, 그렇게 하면 현재 low-recall baseline이 그대로 상위 계약으로 굳어진다.
