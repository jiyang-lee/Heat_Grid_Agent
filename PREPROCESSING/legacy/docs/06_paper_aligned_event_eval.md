# 06-P3. paper-aligned event evaluation 문서

이 문서는 `PREPROCESSING/legacy/osj/06_paper_aligned_event_eval.ipynb`의 목적과 산출물 기준을 정리한다.

## 목적

- event-wise detection rate 계산
- normal event false alarm rate 계산
- detection lead time 계산
- criticality counter 기준 고정

## 핵심 원칙

- window-level 분류 점수만으로 결론 내리지 않는다.
- event 단위로 조기 감지와 오탐을 함께 본다.
- 단발성 spike보다 지속된 이상징후를 우선한다.
- point anomaly 기준은 06-P2의 `train_rmse_p099`를 사용한다.

## 구현 기준

criticality counter 규칙:

```text
anomaly & maintenance 아님 -> +(max(anomaly_score - 1.0, 0.25))
anomaly & maintenance -> 유지
anomaly 아님 -> -1
counter 하한은 0
```

선택 지표:

```text
validation event-wise F0.5
```

이유:

- precision을 recall보다 더 우선한다.
- 논문도 precision 우선 event-wise F-beta를 사용한다.
- 현재 HTML 본문에서는 수식의 beta 표기가 생략되어 있어, 여기서는 precision 우선 구현으로 `beta=0.5`를 명시적으로 고정한다.

## 입력

```text
data/processed/paper_aligned/autoencoder_reconstruction_scores.csv
data/processed/paper_aligned/event_evaluation_windows.csv
```

## 출력

```text
data/processed/paper_aligned/event_detection_summary.csv
data/processed/paper_aligned/event_detection_metrics.csv
data/processed/paper_aligned/event_detection_timeline.csv
data/processed/paper_aligned/event_detection_metadata.json
```

현재 생성 결과:

```text
selected_criticality_threshold: 1.0
point_threshold_name: train_rmse_p099
selection_metric: validation event-wise F0.5
counter_mode: severity_weighted
```

선택된 threshold 기준 성능:

```text
validation:
  fault events 12
  normal events 10
  TP 5 / FN 7 / FP 0 / TN 10
  precision 1.0000
  recall 0.4167
  F0.5 0.7813
  false_alarm_rate 0.0000
  normal_pointwise_accuracy 0.9893
  avg_lead_time_hours_detected_faults 59.76

holdout:
  fault events 11
  normal events 11
  TP 4 / FN 7 / FP 0 / TN 11
  precision 1.0000
  recall 0.3636
  F0.5 0.7407
  false_alarm_rate 0.0000
  normal_pointwise_accuracy 0.9737
  avg_lead_time_hours_detected_faults 31.76
```

감지된 event 수:

```text
validation fault detected: 5
validation normal false alarm: 0
holdout fault detected: 4
holdout normal false alarm: 0
```

## 주의

- 현재 event window는 03번 기존 window 체인을 재사용한다.
- 따라서 논문처럼 모든 fault event에 대해 `report 전 고정 7일 test window`를 완전히 보장하지는 못한다.
- 이 단계 결과는 paper-aligned 근사 baseline으로 해석해야 한다.

## 다음 단계 연결

이 단계 결과는 `06_paper_aligned_agent_contract.ipynb`에서 `risk_score`, `risk_level`, `priority_score` 변환 근거로 사용한다.
