# Anomaly Validity Audit

이 보고서는 6시간 window 기반 anomaly score의 타당성을 검증하기 위한 보조 실험 결과다.

## Generated files

- anomaly_validity_window_length_metrics.csv
- anomaly_validity_window_length_event_leadtime.csv
- anomaly_validity_group_mahalanobis_metrics.csv
- anomaly_validity_group_mahalanobis_event_leadtime.csv
- anomaly_validity_pseudo_clean_false_alarm.csv
- anomaly_validity_event_leadtime.csv
- anomaly_validity_feature_contribution_summary.csv
- anomaly_validity_domain_review_cases.csv
- anomaly_validity_raw_ae_crosscheck.csv

## 1. Window Length Comparison

| window_length_hours | row_count | pre_fault_count | roc_auc | average_precision | precision | recall | f1 | false_positive_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 2364 | 798 | 0.6494 | 0.5646 | 0.7375 | 0.2218 | 0.3410 | 0.0402 |
| 3 | 788 | 266 | 0.6405 | 0.5686 | 0.6442 | 0.2519 | 0.3622 | 0.0709 |
| 6 | 394 | 133 | 0.6266 | 0.5674 | 0.5522 | 0.2782 | 0.3700 | 0.1149 |
| 12 | 195 | 65 | 0.6524 | 0.5999 | 0.5526 | 0.3231 | 0.4078 | 0.1308 |
| 24 | 97 | 31 | 0.6129 | 0.5510 | 0.3421 | 0.4194 | 0.3768 | 0.3788 |

주의: 이 실험은 raw data를 공통 numeric sensor feature로 재집계한 sanity check다. 기존 6시간 engineered feature 모델과 완전히 동일한 feature set은 아니다.

## 2. Group Mahalanobis Comparison

| method | row_count | roc_auc | average_precision | precision | recall | f1 | false_positive_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| global | 394 | 0.6497 | 0.6005 | 0.6271 | 0.2782 | 0.3854 | 0.0843 |
| manufacturer | 394 | 0.6089 | 0.5815 | 0.3905 | 0.4962 | 0.4371 | 0.3946 |
| manufacturer_configuration | 394 | 0.7083 | 0.7394 | 0.3323 | 0.8120 | 0.4716 | 0.8314 |

## 3. Pseudo-clean False Alarm

| policy | normal_rows | pseudo_clean_rows | normal_false_row_rate | pseudo_clean_false_row_rate | false_positive_episodes |
| --- | --- | --- | --- | --- | --- |
| iforest_point | 261 | 251 | 0.0000 | 0.0000 | 0 |
| mahalanobis_point | 261 | 251 | 0.0843 | 0.0876 | 12 |
| ensemble_any | 261 | 251 | 0.0843 | 0.0876 | 12 |
| ensemble_strong | 261 | 251 | 0.0000 | 0.0000 | 0 |
| ensemble_criticality | 261 | 251 | 0.0000 | 0.0000 | 0 |
| raw_ae_q999_c32 | 261 | 251 | 0.0000 | 0.0000 | 0 |
| raw_ae_union | 261 | 251 | 0.0000 | 0.0000 | 0 |
| ensemble_criticality_and_raw_ae | 261 | 251 | 0.0000 | 0.0000 | 0 |
| ensemble_criticality_or_raw_ae | 261 | 251 | 0.0000 | 0.0000 | 0 |

## 4. Event Lead-time

| policy | total_fault_events | detected_fault_events | event_recall | event_recall_24h | event_recall_3d | event_recall_7d | median_first_alarm_lead_hours |
| --- | --- | --- | --- | --- | --- | --- | --- |
| iforest_point | 13 | 3 | 0.2308 | 0.2308 | 0.2308 | 0.2308 | 10.6333 |
| mahalanobis_point | 13 | 8 | 0.6154 | 0.5385 | 0.6154 | 0.6154 | 23.6917 |
| ensemble_any | 13 | 8 | 0.6154 | 0.5385 | 0.6154 | 0.6154 | 23.6917 |
| ensemble_strong | 13 | 3 | 0.2308 | 0.2308 | 0.2308 | 0.2308 | 10.6333 |
| ensemble_criticality | 13 | 2 | 0.1538 | 0.1538 | 0.1538 | 0.1538 | 45.4333 |
| raw_ae_q999_c32 | 13 | 4 | 0.3077 | 0.3077 | 0.3077 | 0.3077 | 35.8976 |
| raw_ae_union | 13 | 5 | 0.3846 | 0.3846 | 0.3846 | 0.3846 | 28.0000 |
| ensemble_criticality_and_raw_ae | 13 | 2 | 0.1538 | 0.1538 | 0.1538 | 0.1538 | 45.4333 |
| ensemble_criticality_or_raw_ae | 13 | 4 | 0.3077 | 0.3077 | 0.3077 | 0.3077 | 35.8976 |

## 5. Feature Contribution Sanity

| category | count | rank_column |
| --- | --- | --- |
| heat_meter | 34 | top1_category |
| temperature_gap | 24 | top1_category |
| temperature | 12 | top1_category |
| control_state | 9 | top1_category |
| data_quality | 1 | top1_category |
| heat_meter | 41 | top2_category |
| temperature_gap | 22 | top2_category |
| temperature | 14 | top2_category |
| data_quality | 2 | top2_category |
| control_state | 1 | top2_category |
| heat_meter | 37 | top3_category |
| temperature | 26 | top3_category |
| temperature_gap | 8 | top3_category |
| data_quality | 8 | top3_category |
| control_state | 1 | top3_category |
| heat_meter | 41 | top4_category |
| temperature | 30 | top4_category |
| temperature_gap | 4 | top4_category |
| flow | 3 | top4_category |
| control_state | 1 | top4_category |
| data_quality | 1 | top4_category |
| heat_meter | 38 | top5_category |
| temperature | 28 | top5_category |
| temperature_gap | 6 | top5_category |
| flow | 6 | top5_category |
| other_sensor_or_context | 1 | top5_category |
| data_quality | 1 | top5_category |

## Interpretation

- Anomaly score는 단독 고장 예측기라기보다 정상 운전 분포 이탈 지표로 해석한다.
- pseudo-clean false alarm과 raw AE 교차검증에서 낮은 false alarm을 보이는 정책은 확증 신호로 쓸 수 있다.
- window length 비교는 기존 6시간 engineered feature와 feature set이 다르므로 방향성 검증으로만 본다.
- top anomaly case는 현장 담당자가 원인 feature를 보고 물리적으로 납득되는지 검토해야 한다.
