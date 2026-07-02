# 06-P5. paper-aligned agent contract 문서

이 문서는 `PREPROCESSING/legacy/osj/06_paper_aligned_agent_contract.ipynb`의 목적과 산출물 기준을 정리한다.

## 목적

- paper-aligned anomaly output을 Agent / Priority Engine 계약 스키마로 변환
- `risk_score`, `risk_level`, `priority_score` 의미를 운영 판단용으로 재정의
- 이력 정보 merge 기준을 고정

## 핵심 원칙

- `risk_score`는 고장 확률이 아니다.
- anomaly score, criticality score, event detection, 이력 정보를 합친 운영 판단 점수다.
- Agent가 바로 문서화할 수 있게 근거 필드를 함께 남긴다.

## 구현 기준

정규화 신호:

```text
normalized_max_anomaly_score = min(max_anomaly_score, 2.0) / 2.0
criticality_score = min(max_counter, 3.0) / 3.0
detection_signal = 1 if detected else 0
history_signal = 0.6 * recent_fault_90d + 0.4 * recent_disturbance_30d
```

risk score:

```text
base_risk_score
= 0.25 * normalized_max_anomaly_score
+ 0.20 * point_anomaly_density
+ 0.20 * criticality_score
+ 0.35 * detection_signal

risk_score
= base_risk_score * (0.45 + 0.55 * detection_signal)
```

priority score:

```text
priority_score
= 100 * (0.75 * risk_score + 0.25 * history_signal)
```

risk level:

```text
low: < 0.30
medium: 0.30 - 0.49
high: 0.50 - 0.74
critical: >= 0.75
```

## 입력

```text
data/processed/paper_aligned/event_detection_summary.csv
data/processed/paper_aligned/autoencoder_reconstruction_scores.csv
data/processed/paper_aligned/main_abnormal_features.csv
data/processed/label_alignment/fault_alignment.csv
data/processed/label_alignment/disturbance_alignment.csv
```

## 출력

```text
data/processed/paper_aligned/agent_contract_output.csv
data/processed/paper_aligned/priority_engine_input.csv
data/processed/paper_aligned/agent_contract_schema.json
data/processed/paper_aligned/agent_contract_metadata.json
```

현재 생성 결과:

```text
contract rows: 44
risk levels:
  critical 5
  high 4
  low 35
```

현재 top priority 예시는 fault event 위주로 정렬된다.

다만 주의:

- 최신 보정 기준에서는 normal event가 `high/critical`로 올라오지 않게 눌렀다.
- detection이 없는 event는 risk score에 추가 게이트를 적용한다.
- 여전히 상단 점수 포화 구간은 남아 있어 이후 calibration 여지는 있다.

## 고정 스키마

```text
substation_id
timestamp
event_id
event_type
manufacturer
configuration_type
anomaly_score
risk_score
risk_level
criticality_score
is_detected
main_abnormal_features
related_fault_history
related_disturbance_history
feature_explanation
priority_score
priority_rank
priority_reason
lead_time_hours
fault_label
event_split
```
