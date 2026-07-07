# Operational Evaluation Comparison

This report compares the current best pipeline as an operational early-warning and prioritization engine.
Window-level metrics check whether each scored window is useful. Substation-level metrics check whether the system can rank which substation should be inspected first on each operating day.

## Alarm Policy Comparison

False alarms are counted on `label == normal`. `clean` is a pseudo-clean subset that excludes recent maintenance/event context when available.

| policy | event_recall | event_recall_24h | median_first_alarm_lead_hours | normal_false_row_rate | false_positive_episodes | false_episodes_per_site_month | clean_false_row_rate | clean_false_rows_per_site_month |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| priority_high_or_urgent | 1.000 | 1.000 | 25.592 | 0.093 | 6 | 3.414 | 0.093 | 11.379 |
| risk_medium_or_higher | 1.000 | 1.000 | 62.008 | 0.299 | 11 | 6.258 | 0.299 | 36.411 |
| risk_high_or_critical | 0.900 | 0.700 | 28.000 | 0.033 | 3 | 1.707 | 0.033 | 3.982 |
| priority_urgent | 0.900 | 0.700 | 28.000 | 0.042 | 4 | 2.276 | 0.042 | 5.120 |
| multi_window_operational | 0.600 | 0.600 | 22.500 | 0.047 | 7 | 3.982 | 0.047 | 5.689 |
| raw_ae_union | 0.400 | 0.400 | 21.367 | 0.033 | 1 | 0.569 | 0.033 | 3.982 |
| raw_ae_q999_c32 | 0.300 | 0.300 | 14.733 | 0.000 | 0 | 0.000 | 0.000 | 0.000 |
| anomaly_event | 0.100 | 0.100 | 63.067 | 0.000 | 0 | 0.000 | 0.000 | 0.000 |

## Window-Level Priority Ranking

This checks whether the highest-scored windows in holdout contain actual pre_fault windows and urgent buckets.

| score | k | precision_at_k | row_recall_at_k | event_recall_at_k | urgent_recall_at_k | ndcg_at_k |
| --- | --- | --- | --- | --- | --- | --- |
| priority_score | 10 | 1.000 | 0.116 | 0.200 | 0.086 | 0.601 |
| priority_score | 20 | 1.000 | 0.233 | 0.600 | 0.286 | 0.656 |
| priority_score | 50 | 0.820 | 0.477 | 0.900 | 0.571 | 0.657 |
| priority_score | 86 | 0.756 | 0.756 | 1.000 | 0.971 | 0.761 |
| priority_score | 100 | 0.710 | 0.826 | 1.000 | 1.000 | 0.796 |
| risk_score | 10 | 0.900 | 0.105 | 0.300 | 0.086 | 0.570 |
| risk_score | 20 | 0.950 | 0.221 | 0.500 | 0.200 | 0.568 |
| risk_score | 50 | 0.800 | 0.465 | 0.800 | 0.686 | 0.678 |
| risk_score | 86 | 0.744 | 0.744 | 1.000 | 0.857 | 0.723 |
| risk_score | 100 | 0.730 | 0.849 | 1.000 | 0.857 | 0.765 |
| anomaly_ensemble_score | 10 | 1.000 | 0.116 | 0.100 | 0.114 | 0.737 |
| anomaly_ensemble_score | 20 | 1.000 | 0.233 | 0.400 | 0.229 | 0.681 |
| anomaly_ensemble_score | 50 | 0.680 | 0.395 | 0.800 | 0.429 | 0.602 |
| anomaly_ensemble_score | 86 | 0.570 | 0.570 | 0.900 | 0.686 | 0.636 |
| anomaly_ensemble_score | 100 | 0.540 | 0.628 | 1.000 | 0.743 | 0.672 |
| mw_anomaly_context_score | 10 | 0.900 | 0.105 | 0.200 | 0.086 | 0.570 |
| mw_anomaly_context_score | 20 | 0.950 | 0.221 | 0.500 | 0.229 | 0.587 |
| mw_anomaly_context_score | 50 | 0.640 | 0.372 | 0.900 | 0.514 | 0.567 |
| mw_anomaly_context_score | 86 | 0.616 | 0.616 | 1.000 | 0.771 | 0.640 |
| mw_anomaly_context_score | 100 | 0.540 | 0.628 | 1.000 | 0.771 | 0.645 |
| multi_horizon_persistence_score | 10 | 1.000 | 0.116 | 0.100 | 0.086 | 0.582 |
| multi_horizon_persistence_score | 20 | 0.950 | 0.221 | 0.300 | 0.257 | 0.626 |
| multi_horizon_persistence_score | 50 | 0.800 | 0.465 | 0.700 | 0.486 | 0.622 |
| multi_horizon_persistence_score | 86 | 0.663 | 0.663 | 0.900 | 0.857 | 0.690 |
| multi_horizon_persistence_score | 100 | 0.590 | 0.686 | 0.900 | 0.886 | 0.703 |
| raw_ae_score_ratio_q999_max | 10 | 1.000 | 0.116 | 0.100 | 0.114 | 0.737 |
| raw_ae_score_ratio_q999_max | 20 | 0.800 | 0.186 | 0.300 | 0.200 | 0.621 |
| raw_ae_score_ratio_q999_max | 50 | 0.620 | 0.360 | 0.800 | 0.514 | 0.588 |
| raw_ae_score_ratio_q999_max | 86 | 0.453 | 0.453 | 0.800 | 0.571 | 0.541 |
| raw_ae_score_ratio_q999_max | 100 | 0.440 | 0.512 | 0.900 | 0.657 | 0.584 |

## Substation-Level Daily Ranking

This aggregates windows by `ranking_date + manufacturer + substation_id`, ranks substations within each day, and evaluates Top-N inspection lists.

| score | date_filter | top_n_substations_per_day | ranking_dates | average_substations_per_date | precision_at_n | station_day_recall_at_n | event_recall_at_n | prefault_date_hit_rate | normal_false_station_day_rate | median_pre_fault_rank |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| priority_score | rankable_2plus | 1 | 21 | 2.381 | 0.429 | 0.529 | 0.800 | 1.000 | 0.364 | 1.000 |
| priority_score | rankable_2plus | 3 | 21 | 2.381 | 0.347 | 1.000 | 1.000 | 1.000 | 0.970 | 1.000 |
| risk_score | rankable_2plus | 1 | 21 | 2.381 | 0.429 | 0.529 | 0.800 | 1.000 | 0.364 | 1.000 |
| risk_score | rankable_2plus | 3 | 21 | 2.381 | 0.347 | 1.000 | 1.000 | 1.000 | 0.970 | 1.000 |
| anomaly_ensemble_score | rankable_2plus | 1 | 21 | 2.381 | 0.429 | 0.529 | 0.800 | 1.000 | 0.364 | 1.000 |
| anomaly_ensemble_score | rankable_2plus | 3 | 21 | 2.381 | 0.347 | 1.000 | 1.000 | 1.000 | 0.970 | 1.000 |
| mw_anomaly_context_score | rankable_2plus | 1 | 21 | 2.381 | 0.429 | 0.529 | 0.800 | 1.000 | 0.364 | 1.000 |
| mw_anomaly_context_score | rankable_2plus | 3 | 21 | 2.381 | 0.347 | 1.000 | 1.000 | 1.000 | 0.970 | 1.000 |
| multi_horizon_persistence_score | rankable_2plus | 1 | 21 | 2.381 | 0.429 | 0.529 | 0.800 | 1.000 | 0.364 | 1.000 |
| multi_horizon_persistence_score | rankable_2plus | 3 | 21 | 2.381 | 0.327 | 0.941 | 1.000 | 1.000 | 1.000 | 1.000 |
| raw_ae_score_ratio_q999_max | rankable_2plus | 1 | 21 | 2.381 | 0.381 | 0.471 | 0.800 | 0.889 | 0.394 | 2.000 |
| raw_ae_score_ratio_q999_max | rankable_2plus | 3 | 21 | 2.381 | 0.347 | 1.000 | 1.000 | 1.000 | 0.970 | 2.000 |

## Interpretation

- High event recall is useful only when the false alarm burden is still operationally acceptable.
- Window-level Top-K can over-count repeated windows from the same substation.
- Substation-level daily Top-N is closer to the real inspection queue: it asks which substations should be checked first.
- The current normal label is pseudo-normal, not a guaranteed field-normal label.
