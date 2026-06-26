# Expanded LGBM Priority 실험: 운영 추론 기준 재검토

## 핵심 결론

이전 `priority_engine_scores_tuned.csv` 기준 결과는 폐기한다. 해당 파일은 leadtime score가 pre_fault 행에만 생성되고 normal 행에는 결측으로 남아, `predicted_lead_time_bucket_missing`이 사실상 정답 힌트로 동작했다.

이번 보고서는 실제 inference package 산출물인 `raw_inference_scores.csv`에서 label join된 `raw_priority_lgbm_vs_rule_labeled_rows.csv`를 기준으로 다시 학습/비교했다. 이 기준에서는 normal에도 leadtime 예측값이 존재하므로 결측 누수 효과가 제거된다.

현재 판정은 `expanded LGBM이 룰베이스를 안정적으로 이겼다`가 아니다. 일부 split과 일부 지표에서 개선 가능성은 보였지만, 운영 baseline은 아직 rule-base가 더 안전하다.

## 데이터

- 입력 기준: `report/priority_model_comparison/raw_priority_lgbm_vs_rule_labeled_rows.csv`
- 학습/비교 rows: `2526`
- feature 수: `209`
- target: normal=0, 3-7d=33, 1-3d=66, 0-24h=100
- 모델 선택: 각 split의 train에서 학습, validation에서 모델/threshold 선택, holdout은 최종 평가에만 사용

Target 분포:

| bucket | count |
| ------ | ----- |
| normal | 1767  |
| 3-7d   | 69    |
| 1-3d   | 427   |
| 0-24h  | 263   |

Leadtime 결측 감사:

| column                         | missing_count | missing_rate |
| ------------------------------ | ------------- | ------------ |
| predicted_lead_time_bucket     | 0             | 0.0000       |
| predicted_lead_time_confidence | 0             | 0.0000       |
| leadtime_prob_0-24h            | 0             | 0.0000       |
| leadtime_prob_1-3d             | 0             | 0.0000       |
| leadtime_prob_3-7d             | 0             | 0.0000       |

Split 감사:

| audit_item                            | count | base |
| ------------------------------------- | ----- | ---- |
| fault_event_id_cross_split_time_based | 10    | 52   |

## 명시적으로 제외한 입력

```text
priority_score
priority_level
priority_reason
risk_base_score
risk_probability_component_score
leadtime_component_score
anomaly_component_score
history_adjustment_score
lead_time_bucket_distance
lead_time_target
predicted_lead_time_index
label / fault_event_id / estimated_lead_time_hours 등 정답/식별자 계열
```

## Validation 선택 결과

| split_strategy         | model_key        | selection_score | selected_action_threshold | mae     | spearman | ndcg@R | recall@100 | action_precision | action_recall | action_f1 | fp | fn | best_iteration |
| ---------------------- | ---------------- | --------------- | ------------------------- | ------- | -------- | ------ | ---------- | ---------------- | ------------- | --------- | -- | -- | -------------- |
| split_regime_based     | expanded_lgbm_03 | 2.1156          | 36.2500                   | 26.8208 | 0.6274   | 0.7517 | 0.6542     | 0.6000           | 0.9375        | 0.7317    | 60 | 6  | 17             |
| split_substation_based | expanded_lgbm_03 | 2.7616          | 47.0000                   | 13.4391 | 0.6813   | 0.8993 | 1.0000     | 0.9792           | 0.8868        | 0.9307    | 1  | 6  | 202            |
| split_time_based       | expanded_lgbm_01 | 2.2315          | 27.7500                   | 20.0187 | 0.6052   | 0.8255 | 0.6807     | 0.6935           | 0.8269        | 0.7544    | 38 | 18 | 56             |

## Holdout 비교

| split                          | model_key                  | n   | mae     | rmse    | spearman | precision@R | recall@R | ndcg@R | precision@100 | recall@100 | ndcg@100 | action_threshold | action_precision | action_recall | action_f1 | action_specificity | action_rate | fp | fn |
| ------------------------------ | -------------------------- | --- | ------- | ------- | -------- | ----------- | -------- | ------ | ------------- | ---------- | -------- | ---------------- | ---------------- | ------------- | --------- | ------------------ | ----------- | -- | -- |
| split_time_based_holdout       | rule_base_raw_inference    | 394 | 30.1315 | 35.3939 | 0.4317   | 0.6617      | 0.6617   | 0.7089 | 0.7100        | 0.5338     | 0.7054   | 48.0000          | 0.6341           | 0.6240        | 0.6290    | 0.8327             | 0.3122      | 45 | 47 |
| split_time_based_holdout       | team_7feature_lgbm_raw     | 394 | 26.2543 | 33.9125 | 0.4730   | 0.6015      | 0.6015   | 0.6270 | 0.6400        | 0.4812     | 0.6248   | 49.5000          | 0.7105           | 0.2160        | 0.3313    | 0.9591             | 0.0964      | 11 | 98 |
| split_time_based_holdout       | expanded_lgbm_raw_upstream | 394 | 23.5791 | 32.6314 | 0.5598   | 0.7068      | 0.7068   | 0.6413 | 0.7000        | 0.5263     | 0.6125   | 27.7500          | 0.6549           | 0.7440        | 0.6966    | 0.8178             | 0.3604      | 49 | 32 |
| split_substation_based_holdout | rule_base_raw_inference    | 256 | 23.9484 | 27.8777 | 0.5538   | 0.7385      | 0.7385   | 0.8050 | 0.5300        | 0.8154     | 0.8524   | 48.0000          | 0.9375           | 0.6923        | 0.7965    | 0.9843             | 0.1875      | 3  | 20 |
| split_substation_based_holdout | team_7feature_lgbm_raw     | 256 | 24.7983 | 33.9046 | 0.4164   | 0.5231      | 0.5231   | 0.6153 | 0.4600        | 0.7077     | 0.7344   | 49.5000          | 0.6250           | 0.4615        | 0.5310    | 0.9058             | 0.1875      | 18 | 35 |
| split_substation_based_holdout | expanded_lgbm_raw_upstream | 256 | 13.4434 | 25.9050 | 0.4608   | 0.7077      | 0.7077   | 0.7764 | 0.5000        | 0.7692     | 0.8168   | 47.0000          | 0.9722           | 0.5385        | 0.6931    | 0.9948             | 0.1406      | 1  | 30 |
| split_regime_based_holdout     | rule_base_raw_inference    | 341 | 28.9629 | 33.9494 | 0.5443   | 0.7333      | 0.7333   | 0.7797 | 0.7700        | 0.6417     | 0.7856   | 48.0000          | 0.6983           | 0.7043        | 0.7013    | 0.8451             | 0.3402      | 35 | 34 |
| split_regime_based_holdout     | team_7feature_lgbm_raw     | 341 | 25.0902 | 33.1284 | 0.4587   | 0.6167      | 0.6167   | 0.7029 | 0.6600        | 0.5500     | 0.7122   | 49.5000          | 0.9474           | 0.4696        | 0.6279    | 0.9867             | 0.1672      | 3  | 61 |
| split_regime_based_holdout     | expanded_lgbm_raw_upstream | 341 | 31.1895 | 34.9313 | 0.5290   | 0.6583      | 0.6583   | 0.7425 | 0.6500        | 0.5417     | 0.7345   | 36.2500          | 0.6369           | 0.8696        | 0.7353    | 0.7478             | 0.4604      | 57 | 15 |

## 상위 Feature Importance

| split_strategy         | original_feature                            | importance |
| ---------------------- | ------------------------------------------- | ---------- |
| split_regime_based     | risk_score                                  | 36         |
| split_regime_based     | doy_cos                                     | 16         |
| split_regime_based     | leadtime_prob_0-24h                         | 16         |
| split_regime_based     | days_since_last_any_event                   | 15         |
| split_regime_based     | p_net_meter_volume__first                   | 15         |
| split_regime_based     | day_of_year                                 | 11         |
| split_regime_based     | configuration_type__is__sh_with_buffer_tank | 9          |
| split_regime_based     | hc1_supply_temperature_gap__max_abs         | 6          |
| split_regime_based     | predicted_lead_time_bucket_0-24h            | 6          |
| split_regime_based     | p_net_meter_energy__first                   | 5          |
| split_regime_based     | p_net_meter_volume__min                     | 5          |
| split_regime_based     | leadtime_prob_1-3d                          | 5          |
| split_regime_based     | leadtime_prob_3-7d                          | 5          |
| split_regime_based     | doy_sin                                     | 4          |
| split_regime_based     | s_dhw_3-way_valve_status__dominant__is__ein | 4          |
| split_substation_based | risk_score                                  | 235        |
| split_substation_based | days_since_last_any_event                   | 233        |
| split_substation_based | doy_cos                                     | 127        |
| split_substation_based | doy_sin                                     | 121        |
| split_substation_based | leadtime_prob_0-24h                         | 114        |
| split_substation_based | day_of_year                                 | 89         |
| split_substation_based | risk_probability                            | 75         |
| split_substation_based | leadtime_prob_3-7d                          | 58         |
| split_substation_based | p_hc1_return_temperature__mean              | 55         |
| split_substation_based | leadtime_prob_1-3d                          | 48         |
| split_substation_based | days_since_last_task_event                  | 47         |
| split_substation_based | risk_level_calibrated_high                  | 46         |
| split_substation_based | p_net_meter_energy__first                   | 44         |
| split_substation_based | s_dhw_lower_storage_temperature__max        | 43         |
| split_substation_based | p_net_supply_temperature__min               | 36         |
| split_time_based       | risk_score                                  | 75         |
| split_time_based       | leadtime_prob_0-24h                         | 42         |
| split_time_based       | doy_cos                                     | 29         |
| split_time_based       | configuration_type__is__sh_with_buffer_tank | 20         |
| split_time_based       | days_since_last_any_event                   | 19         |
| split_time_based       | risk_probability                            | 17         |
| split_time_based       | leadtime_prob_1-3d                          | 16         |
| split_time_based       | leadtime_prob_3-7d                          | 15         |
| split_time_based       | p_net_meter_energy__first                   | 12         |
| split_time_based       | outdoor_temperature__mean                   | 7          |
| split_time_based       | hc1_supply_temperature_gap__max_abs         | 6          |
| split_time_based       | s_dhw_lower_storage_temperature__first      | 6          |
| split_time_based       | anomaly_score                               | 6          |
| split_time_based       | doy_sin                                     | 5          |
| split_time_based       | p_net_meter_energy__mean                    | 5          |

## 해석

- `split_time_based_holdout`: expanded LGBM은 MAE와 high/urgent F1은 개선했지만, NDCG@R은 rule-base보다 낮다.
- `split_substation_based_holdout`: 새 설비/미등장 설비 관점에서는 rule-base가 F1과 NDCG@R 모두 더 안정적이다.
- `split_regime_based_holdout`: expanded LGBM은 recall/F1은 높지만, MAE와 NDCG@R은 rule-base보다 나쁘다.

## 최종 판정

누수 제거 후에는 expanded LGBM이 룰베이스를 압도하지 않는다. 운영 자동화 기준에서는 rule-base를 baseline으로 유지하고, expanded LGBM은 추가 검증 후보로 보는 것이 맞다.

다음 단계는 priority head를 바로 교체하는 것이 아니라, upstream output을 out-of-fold 방식으로 만들고 fault-event group split까지 포함해 다시 검증하는 것이다.

## 산출물

- report: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_report.md`
- metrics: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_metrics.csv`
- validation selection: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_selection.csv`
- feature mapping: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_features.csv`
- feature importance: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_feature_importance.csv`
- predictions: `report/priority_model_comparison/expanded_lgbm_priority_no_rule_predictions.csv`
- model bundle: `report/priority_model_comparison/models/expanded_lgbm_priority_no_rule.joblib`
