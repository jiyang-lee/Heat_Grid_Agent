# 상황별 샘플링 LGBM Priority 실험

## 목적

룰베이스를 바로 대체할 수 있는지 보기 위해, 운영 추론 기준 데이터에서 상황별 train weighting/resampling을 적용한 LGBM priority head를 다시 실험했다.

중요한 검증 원칙:

- 샘플링/가중치는 train split에만 적용했다.
- validation/holdout은 원분포 그대로 유지했다.
- 모델과 action threshold는 validation에서만 선택했다.
- holdout은 최종 비교에만 사용했다.
- 룰베이스 점수/component/정답/식별자 계열은 feature에서 제외했다.

## 데이터

- 입력: `report/priority_model_comparison/raw_priority_lgbm_vs_rule_labeled_rows.csv`
- rows: `2526`
- leadtime 결측 누수 제거 기준: normal/pre_fault 모두 upstream leadtime 예측값 존재

## 실험 전략

| sampling_strategy          | description                                                                       |
| -------------------------- | --------------------------------------------------------------------------------- |
| baseline_no_weight         | No train sampling or weighting.                                                   |
| severity_weighted          | Upweight 0-24h/1-3d/3-7d pre-fault rows and slightly downweight normal rows.      |
| hard_case_weighted         | Upweight hard negatives and low-signal positives based on upstream model outputs. |
| event_balanced             | Equalize pre-fault fault_event_id contribution inside train.                      |
| substation_balanced        | Reduce dominance of high-row-count substations inside train.                      |
| combined_context_weighted  | Combine severity, hard-case, event, and substation weighting.                     |
| combined_context_resampled | Sample train rows with replacement using combined context weights.                |

## 핵심 결과

| split                          | rule_f1 | best_lgbm_f1_strategy | best_lgbm_f1 | f1_delta | rule_ndcg@R | best_lgbm_ndcg@R | ndcg_delta | fp_delta | fn_delta | best_lgbm_ndcg_strategy | max_lgbm_ndcg@R | verdict           |
| ------------------------------ | ------- | --------------------- | ------------ | -------- | ----------- | ---------------- | ---------- | -------- | -------- | ----------------------- | --------------- | ----------------- |
| split_regime_based_holdout     | 0.7013  | severity_weighted     | 0.7634       | 0.0621   | 0.7797      | 0.7711           | -0.0086    | 12       | -19      | severity_weighted       | 0.7711          | F1 개선, ranking 미달 |
| split_substation_based_holdout | 0.7965  | hard_case_weighted    | 0.7748       | -0.0217  | 0.8050      | 0.7942           | -0.0108    | 0        | 2        | hard_case_weighted      | 0.7942          | rule-base 우세      |
| split_time_based_holdout       | 0.6290  | hard_case_weighted    | 0.6970       | 0.0679   | 0.7089      | 0.6962           | -0.0127    | 2        | -14      | hard_case_weighted      | 0.6962          | F1 개선, ranking 미달 |

요약하면 샘플링/가중치로 `time`과 `regime` holdout의 action F1은 개선됐지만, `substation` holdout에서는 rule-base가 아직 더 안정적이다. 특히 새 설비 일반화 기준에서는 LGBM이 F1과 NDCG@R을 동시에 넘지 못했다.

## Train Weight 요약

| split_strategy         | sampling_strategy          | min    | mean   | max     |
| ---------------------- | -------------------------- | ------ | ------ | ------- |
| split_time_based       | baseline_no_weight         | 1.0000 | 1.0000 | 1.0000  |
| split_time_based       | severity_weighted          | 0.5113 | 1.0000 | 2.7270  |
| split_time_based       | hard_case_weighted         | 0.6888 | 1.0000 | 1.9286  |
| split_time_based       | event_balanced             | 0.7620 | 1.0000 | 4.0322  |
| split_time_based       | substation_balanced        | 0.5935 | 1.0000 | 3.9520  |
| split_time_based       | combined_context_weighted  | 0.2000 | 0.9674 | 10.0000 |
| split_time_based       | combined_context_resampled | 0.2000 | 0.9718 | 12.0000 |
| split_substation_based | baseline_no_weight         | 1.0000 | 1.0000 | 1.0000  |
| split_substation_based | severity_weighted          | 0.4883 | 1.0000 | 2.6044  |
| split_substation_based | hard_case_weighted         | 0.6913 | 1.0000 | 1.9357  |
| split_substation_based | event_balanced             | 0.5781 | 1.0000 | 4.2485  |
| split_substation_based | substation_balanced        | 0.5982 | 1.0000 | 3.9831  |
| split_substation_based | combined_context_weighted  | 0.2000 | 0.9678 | 10.0000 |
| split_substation_based | combined_context_resampled | 0.2000 | 0.9728 | 12.0000 |
| split_regime_based     | baseline_no_weight         | 1.0000 | 1.0000 | 1.0000  |
| split_regime_based     | severity_weighted          | 0.5034 | 1.0000 | 2.6847  |
| split_regime_based     | hard_case_weighted         | 0.6889 | 1.0000 | 1.9288  |
| split_regime_based     | event_balanced             | 0.7259 | 1.0000 | 4.0418  |
| split_regime_based     | substation_balanced        | 0.5451 | 1.0000 | 4.4449  |
| split_regime_based     | combined_context_weighted  | 0.2000 | 0.9321 | 10.0000 |
| split_regime_based     | combined_context_resampled | 0.2000 | 0.9456 | 12.0000 |

## Validation 선택 결과

| split_strategy         | sampling_strategy          | model_key        | selection_score | selected_action_threshold | mae     | ndcg@R | action_precision | action_recall | action_f1 | fp  | fn | best_iteration |
| ---------------------- | -------------------------- | ---------------- | --------------- | ------------------------- | ------- | ------ | ---------------- | ------------- | --------- | --- | -- | -------------- |
| split_regime_based     | baseline_no_weight         | expanded_lgbm_03 | 2.1156          | 36.2500                   | 26.8208 | 0.7517 | 0.6000           | 0.9375        | 0.7317    | 60  | 6  | 17             |
| split_regime_based     | combined_context_resampled | expanded_lgbm_05 | 1.7814          | 59.0000                   | 29.6011 | 0.6611 | 0.5245           | 0.7812        | 0.6276    | 68  | 21 | 887            |
| split_regime_based     | combined_context_weighted  | expanded_lgbm_05 | 1.7720          | 53.5000                   | 31.7980 | 0.6609 | 0.4860           | 0.9062        | 0.6327    | 92  | 9  | 305            |
| split_regime_based     | event_balanced             | expanded_lgbm_01 | 2.0906          | 40.7500                   | 28.0908 | 0.7430 | 0.6181           | 0.9271        | 0.7417    | 55  | 7  | 17             |
| split_regime_based     | hard_case_weighted         | expanded_lgbm_05 | 2.0993          | 46.7500                   | 20.3622 | 0.7556 | 0.6081           | 0.9375        | 0.7377    | 58  | 6  | 30             |
| split_regime_based     | severity_weighted          | expanded_lgbm_04 | 1.6789          | 55.2500                   | 39.3423 | 0.6404 | 0.4938           | 0.8333        | 0.6202    | 82  | 16 | 16             |
| split_regime_based     | substation_balanced        | expanded_lgbm_01 | 1.7995          | 44.5000                   | 28.9013 | 0.6707 | 0.4603           | 0.9062        | 0.6105    | 102 | 9  | 21             |
| split_substation_based | baseline_no_weight         | expanded_lgbm_03 | 2.7616          | 47.0000                   | 13.4391 | 0.8993 | 0.9792           | 0.8868        | 0.9307    | 1   | 6  | 202            |
| split_substation_based | combined_context_resampled | expanded_lgbm_01 | 2.3734          | 61.5000                   | 18.9115 | 0.8079 | 0.8444           | 0.7170        | 0.7755    | 7   | 15 | 196            |
| split_substation_based | combined_context_weighted  | expanded_lgbm_04 | 2.3825          | 62.2500                   | 16.1780 | 0.7697 | 0.9444           | 0.6415        | 0.7640    | 2   | 19 | 219            |
| split_substation_based | event_balanced             | expanded_lgbm_03 | 2.6450          | 41.7500                   | 14.2453 | 0.8875 | 0.9020           | 0.8679        | 0.8846    | 5   | 7  | 118            |
| split_substation_based | hard_case_weighted         | expanded_lgbm_01 | 2.7539          | 32.2500                   | 12.3339 | 0.8877 | 0.8814           | 0.9811        | 0.9286    | 7   | 1  | 132            |
| split_substation_based | severity_weighted          | expanded_lgbm_05 | 2.4744          | 55.2500                   | 15.7998 | 0.7962 | 0.8837           | 0.7170        | 0.7917    | 5   | 15 | 157            |
| split_substation_based | substation_balanced        | expanded_lgbm_06 | 2.5959          | 43.0000                   | 15.3739 | 0.8685 | 0.8654           | 0.8491        | 0.8571    | 7   | 8  | 88             |
| split_time_based       | baseline_no_weight         | expanded_lgbm_01 | 2.2315          | 27.7500                   | 20.0187 | 0.8255 | 0.6935           | 0.8269        | 0.7544    | 38  | 18 | 56             |
| split_time_based       | combined_context_resampled | expanded_lgbm_06 | 1.7496          | 54.7500                   | 27.2901 | 0.7002 | 0.5280           | 0.6346        | 0.5764    | 59  | 38 | 899            |
| split_time_based       | combined_context_weighted  | expanded_lgbm_01 | 1.7835          | 61.7500                   | 27.2850 | 0.6835 | 0.6344           | 0.5673        | 0.5990    | 34  | 45 | 123            |
| split_time_based       | event_balanced             | expanded_lgbm_01 | 2.0333          | 30.0000                   | 21.9115 | 0.7617 | 0.6098           | 0.7212        | 0.6608    | 48  | 29 | 52             |
| split_time_based       | hard_case_weighted         | expanded_lgbm_01 | 2.2394          | 31.2500                   | 19.6927 | 0.8234 | 0.6935           | 0.8269        | 0.7544    | 38  | 18 | 45             |
| split_time_based       | severity_weighted          | expanded_lgbm_02 | 2.0432          | 58.2500                   | 23.9798 | 0.7527 | 0.7041           | 0.6635        | 0.6832    | 29  | 35 | 607            |
| split_time_based       | substation_balanced        | expanded_lgbm_01 | 2.1495          | 40.7500                   | 21.3650 | 0.7939 | 0.7347           | 0.6923        | 0.7129    | 26  | 32 | 42             |

## Holdout 전체 비교

| split                          | model_key                  | n   | mae     | spearman | ndcg@R | recall@100 | action_threshold | action_precision | action_recall | action_f1 | fp  | fn |
| ------------------------------ | -------------------------- | --- | ------- | -------- | ------ | ---------- | ---------------- | ---------------- | ------------- | --------- | --- | -- |
| split_regime_based_holdout     | severity_weighted          | 341 | 39.4790 | 0.5805   | 0.7711 | 0.6083     | 55.2500          | 0.6803           | 0.8696        | 0.7634    | 47  | 15 |
| split_regime_based_holdout     | event_balanced             | 341 | 33.0131 | 0.5240   | 0.7201 | 0.5000     | 40.7500          | 0.6667           | 0.8696        | 0.7547    | 50  | 15 |
| split_regime_based_holdout     | hard_case_weighted         | 341 | 25.6518 | 0.5398   | 0.7522 | 0.5750     | 46.7500          | 0.6516           | 0.8783        | 0.7481    | 54  | 14 |
| split_regime_based_holdout     | baseline_no_weight         | 341 | 31.1895 | 0.5290   | 0.7425 | 0.5417     | 36.2500          | 0.6369           | 0.8696        | 0.7353    | 57  | 15 |
| split_regime_based_holdout     | rule_base_raw_inference    | 341 | 28.9629 | 0.5443   | 0.7797 | 0.6417     | 48.0000          | 0.6983           | 0.7043        | 0.7013    | 35  | 34 |
| split_regime_based_holdout     | substation_balanced        | 341 | 33.9369 | 0.4635   | 0.6797 | 0.4500     | 44.5000          | 0.5893           | 0.8609        | 0.6996    | 69  | 16 |
| split_regime_based_holdout     | combined_context_weighted  | 341 | 32.1794 | 0.5304   | 0.7166 | 0.5333     | 53.5000          | 0.5543           | 0.8870        | 0.6823    | 82  | 13 |
| split_regime_based_holdout     | combined_context_resampled | 341 | 32.0498 | 0.4811   | 0.6833 | 0.5083     | 59.0000          | 0.5935           | 0.8000        | 0.6815    | 63  | 23 |
| split_regime_based_holdout     | team_7feature_lgbm_raw     | 341 | 25.0902 | 0.4587   | 0.7029 | 0.5500     | 49.5000          | 0.9474           | 0.4696        | 0.6279    | 3   | 61 |
| split_substation_based_holdout | rule_base_raw_inference    | 256 | 23.9484 | 0.5538   | 0.8050 | 0.8154     | 48.0000          | 0.9375           | 0.6923        | 0.7965    | 3   | 20 |
| split_substation_based_holdout | hard_case_weighted         | 256 | 12.7623 | 0.4873   | 0.7942 | 0.8000     | 32.2500          | 0.9348           | 0.6615        | 0.7748    | 3   | 22 |
| split_substation_based_holdout | combined_context_resampled | 256 | 21.5641 | 0.5190   | 0.7782 | 0.7846     | 61.5000          | 0.9318           | 0.6308        | 0.7523    | 3   | 24 |
| split_substation_based_holdout | combined_context_weighted  | 256 | 19.0515 | 0.4895   | 0.7637 | 0.7538     | 62.2500          | 0.9250           | 0.5692        | 0.7048    | 3   | 28 |
| split_substation_based_holdout | substation_balanced        | 256 | 15.7868 | 0.4253   | 0.7741 | 0.7385     | 43.0000          | 0.9474           | 0.5538        | 0.6990    | 2   | 29 |
| split_substation_based_holdout | baseline_no_weight         | 256 | 13.4434 | 0.4608   | 0.7764 | 0.7692     | 47.0000          | 0.9722           | 0.5385        | 0.6931    | 1   | 30 |
| split_substation_based_holdout | event_balanced             | 256 | 14.2945 | 0.4652   | 0.7635 | 0.7846     | 41.7500          | 0.8974           | 0.5385        | 0.6731    | 4   | 30 |
| split_substation_based_holdout | severity_weighted          | 256 | 22.4112 | 0.4997   | 0.7406 | 0.7231     | 55.2500          | 0.7400           | 0.5692        | 0.6435    | 13  | 28 |
| split_substation_based_holdout | team_7feature_lgbm_raw     | 256 | 24.7983 | 0.4164   | 0.6153 | 0.7077     | 49.5000          | 0.6250           | 0.4615        | 0.5310    | 18  | 35 |
| split_time_based_holdout       | hard_case_weighted         | 394 | 22.6360 | 0.5387   | 0.6962 | 0.4962     | 31.2500          | 0.6619           | 0.7360        | 0.6970    | 47  | 33 |
| split_time_based_holdout       | baseline_no_weight         | 394 | 23.5791 | 0.5598   | 0.6413 | 0.5263     | 27.7500          | 0.6549           | 0.7440        | 0.6966    | 49  | 32 |
| split_time_based_holdout       | substation_balanced        | 394 | 26.1985 | 0.5395   | 0.6779 | 0.5263     | 40.7500          | 0.6275           | 0.7680        | 0.6906    | 57  | 29 |
| split_time_based_holdout       | event_balanced             | 394 | 25.2899 | 0.5565   | 0.6898 | 0.5263     | 30.0000          | 0.6294           | 0.7200        | 0.6716    | 53  | 35 |
| split_time_based_holdout       | severity_weighted          | 394 | 28.2216 | 0.5111   | 0.6581 | 0.5865     | 58.2500          | 0.6512           | 0.6720        | 0.6614    | 45  | 41 |
| split_time_based_holdout       | rule_base_raw_inference    | 394 | 30.1315 | 0.4317   | 0.7089 | 0.5338     | 48.0000          | 0.6341           | 0.6240        | 0.6290    | 45  | 47 |
| split_time_based_holdout       | combined_context_weighted  | 394 | 30.6764 | 0.4928   | 0.6392 | 0.4962     | 61.7500          | 0.5870           | 0.6480        | 0.6160    | 57  | 44 |
| split_time_based_holdout       | combined_context_resampled | 394 | 31.9393 | 0.4333   | 0.5904 | 0.4361     | 54.7500          | 0.4673           | 0.7440        | 0.5741    | 106 | 32 |
| split_time_based_holdout       | team_7feature_lgbm_raw     | 394 | 26.2543 | 0.4730   | 0.6270 | 0.4812     | 49.5000          | 0.7105           | 0.2160        | 0.3313    | 11  | 98 |

## Split별 상위 LGBM 후보

| split                          | model_key                  | n   | mae     | spearman | ndcg@R | recall@100 | action_threshold | action_precision | action_recall | action_f1 | fp | fn |
| ------------------------------ | -------------------------- | --- | ------- | -------- | ------ | ---------- | ---------------- | ---------------- | ------------- | --------- | -- | -- |
| split_regime_based_holdout     | severity_weighted          | 341 | 39.4790 | 0.5805   | 0.7711 | 0.6083     | 55.2500          | 0.6803           | 0.8696        | 0.7634    | 47 | 15 |
| split_regime_based_holdout     | event_balanced             | 341 | 33.0131 | 0.5240   | 0.7201 | 0.5000     | 40.7500          | 0.6667           | 0.8696        | 0.7547    | 50 | 15 |
| split_regime_based_holdout     | hard_case_weighted         | 341 | 25.6518 | 0.5398   | 0.7522 | 0.5750     | 46.7500          | 0.6516           | 0.8783        | 0.7481    | 54 | 14 |
| split_substation_based_holdout | hard_case_weighted         | 256 | 12.7623 | 0.4873   | 0.7942 | 0.8000     | 32.2500          | 0.9348           | 0.6615        | 0.7748    | 3  | 22 |
| split_substation_based_holdout | combined_context_resampled | 256 | 21.5641 | 0.5190   | 0.7782 | 0.7846     | 61.5000          | 0.9318           | 0.6308        | 0.7523    | 3  | 24 |
| split_substation_based_holdout | combined_context_weighted  | 256 | 19.0515 | 0.4895   | 0.7637 | 0.7538     | 62.2500          | 0.9250           | 0.5692        | 0.7048    | 3  | 28 |
| split_time_based_holdout       | hard_case_weighted         | 394 | 22.6360 | 0.5387   | 0.6962 | 0.4962     | 31.2500          | 0.6619           | 0.7360        | 0.6970    | 47 | 33 |
| split_time_based_holdout       | baseline_no_weight         | 394 | 23.5791 | 0.5598   | 0.6413 | 0.5263     | 27.7500          | 0.6549           | 0.7440        | 0.6966    | 49 | 32 |
| split_time_based_holdout       | substation_balanced        | 394 | 26.1985 | 0.5395   | 0.6779 | 0.5263     | 40.7500          | 0.6275           | 0.7680        | 0.6906    | 57 | 29 |

## 상위 Feature Importance

| split_strategy         | sampling_strategy          | original_feature                            | importance |
| ---------------------- | -------------------------- | ------------------------------------------- | ---------- |
| split_regime_based     | baseline_no_weight         | risk_score                                  | 36         |
| split_regime_based     | baseline_no_weight         | doy_cos                                     | 16         |
| split_regime_based     | baseline_no_weight         | leadtime_prob_0-24h                         | 16         |
| split_regime_based     | baseline_no_weight         | days_since_last_any_event                   | 15         |
| split_regime_based     | baseline_no_weight         | p_net_meter_volume__first                   | 15         |
| split_regime_based     | baseline_no_weight         | day_of_year                                 | 11         |
| split_regime_based     | baseline_no_weight         | configuration_type__is__sh_with_buffer_tank | 9          |
| split_regime_based     | baseline_no_weight         | hc1_supply_temperature_gap__max_abs         | 6          |
| split_regime_based     | combined_context_resampled | days_since_last_any_event                   | 342        |
| split_regime_based     | combined_context_resampled | risk_score                                  | 238        |
| split_regime_based     | combined_context_resampled | leadtime_prob_0-24h                         | 192        |
| split_regime_based     | combined_context_resampled | doy_sin                                     | 174        |
| split_regime_based     | combined_context_resampled | doy_cos                                     | 156        |
| split_regime_based     | combined_context_resampled | day_of_year                                 | 128        |
| split_regime_based     | combined_context_resampled | p_net_meter_flow__std                       | 124        |
| split_regime_based     | combined_context_resampled | predicted_lead_time_confidence              | 118        |
| split_regime_based     | combined_context_weighted  | risk_score                                  | 161        |
| split_regime_based     | combined_context_weighted  | leadtime_prob_0-24h                         | 130        |
| split_regime_based     | combined_context_weighted  | doy_cos                                     | 109        |
| split_regime_based     | combined_context_weighted  | days_since_last_any_event                   | 84         |
| split_regime_based     | combined_context_weighted  | doy_sin                                     | 75         |
| split_regime_based     | combined_context_weighted  | anomaly_score                               | 61         |
| split_regime_based     | combined_context_weighted  | day_of_year                                 | 54         |
| split_regime_based     | combined_context_weighted  | p_net_meter_energy__first                   | 43         |
| split_regime_based     | event_balanced             | risk_score                                  | 18         |
| split_regime_based     | event_balanced             | leadtime_prob_0-24h                         | 14         |
| split_regime_based     | event_balanced             | doy_cos                                     | 11         |
| split_regime_based     | event_balanced             | p_net_meter_volume__first                   | 11         |
| split_regime_based     | event_balanced             | configuration_type__is__sh_with_buffer_tank | 7          |
| split_regime_based     | event_balanced             | s_dhw_3-way_valve_status__dominant__is__ein | 7          |
| split_regime_based     | event_balanced             | risk_probability                            | 7          |
| split_regime_based     | event_balanced             | risk_level_calibrated_medium                | 6          |
| split_regime_based     | hard_case_weighted         | risk_score                                  | 35         |
| split_regime_based     | hard_case_weighted         | p_net_meter_volume__first                   | 29         |
| split_regime_based     | hard_case_weighted         | doy_cos                                     | 20         |
| split_regime_based     | hard_case_weighted         | leadtime_prob_0-24h                         | 16         |
| split_regime_based     | hard_case_weighted         | anomaly_score                               | 13         |
| split_regime_based     | hard_case_weighted         | configuration_type__is__sh_with_buffer_tank | 12         |
| split_regime_based     | hard_case_weighted         | s_dhw_3-way_valve_status__dominant__is__ein | 9          |
| split_regime_based     | hard_case_weighted         | days_since_last_any_event                   | 8          |
| split_regime_based     | severity_weighted          | risk_score                                  | 52         |
| split_regime_based     | severity_weighted          | days_since_last_any_event                   | 21         |
| split_regime_based     | severity_weighted          | configuration_type__is__sh_with_buffer_tank | 12         |
| split_regime_based     | severity_weighted          | leadtime_prob_0-24h                         | 12         |
| split_regime_based     | severity_weighted          | leadtime_prob_1-3d                          | 12         |
| split_regime_based     | severity_weighted          | p_net_meter_volume__last                    | 10         |
| split_regime_based     | severity_weighted          | hc1_supply_temperature_gap__max_abs         | 10         |
| split_regime_based     | severity_weighted          | s_dhw_lower_storage_temperature__std        | 9          |
| split_regime_based     | substation_balanced        | risk_score                                  | 27         |
| split_regime_based     | substation_balanced        | leadtime_prob_0-24h                         | 18         |
| split_regime_based     | substation_balanced        | doy_cos                                     | 17         |
| split_regime_based     | substation_balanced        | configuration_type__is__sh_with_buffer_tank | 11         |
| split_regime_based     | substation_balanced        | p_net_meter_volume__first                   | 10         |
| split_regime_based     | substation_balanced        | risk_level_calibrated_medium                | 9          |
| split_regime_based     | substation_balanced        | p_net_meter_energy__first                   | 7          |
| split_regime_based     | substation_balanced        | s_dhw_3-way_valve_status__dominant__is__ein | 6          |
| split_substation_based | baseline_no_weight         | risk_score                                  | 235        |
| split_substation_based | baseline_no_weight         | days_since_last_any_event                   | 233        |
| split_substation_based | baseline_no_weight         | doy_cos                                     | 127        |
| split_substation_based | baseline_no_weight         | doy_sin                                     | 121        |
| split_substation_based | baseline_no_weight         | leadtime_prob_0-24h                         | 114        |
| split_substation_based | baseline_no_weight         | day_of_year                                 | 89         |
| split_substation_based | baseline_no_weight         | risk_probability                            | 75         |
| split_substation_based | baseline_no_weight         | leadtime_prob_3-7d                          | 58         |
| split_substation_based | combined_context_resampled | risk_score                                  | 147        |
| split_substation_based | combined_context_resampled | days_since_last_any_event                   | 107        |
| split_substation_based | combined_context_resampled | leadtime_prob_0-24h                         | 72         |
| split_substation_based | combined_context_resampled | doy_sin                                     | 44         |
| split_substation_based | combined_context_resampled | leadtime_prob_3-7d                          | 39         |
| split_substation_based | combined_context_resampled | configuration_type__is__sh_with_buffer_tank | 27         |
| split_substation_based | combined_context_resampled | risk_probability                            | 27         |
| split_substation_based | combined_context_resampled | s_hc1_supply_temperature__std               | 25         |
| split_substation_based | combined_context_weighted  | risk_score                                  | 272        |
| split_substation_based | combined_context_weighted  | days_since_last_any_event                   | 175        |
| split_substation_based | combined_context_weighted  | leadtime_prob_0-24h                         | 140        |
| split_substation_based | combined_context_weighted  | doy_sin                                     | 132        |
| split_substation_based | combined_context_weighted  | risk_probability                            | 109        |
| split_substation_based | combined_context_weighted  | doy_cos                                     | 106        |
| split_substation_based | combined_context_weighted  | leadtime_prob_3-7d                          | 103        |
| split_substation_based | combined_context_weighted  | day_of_year                                 | 76         |
| split_substation_based | event_balanced             | risk_score                                  | 201        |
| split_substation_based | event_balanced             | days_since_last_any_event                   | 183        |
| split_substation_based | event_balanced             | leadtime_prob_0-24h                         | 98         |
| split_substation_based | event_balanced             | doy_cos                                     | 76         |
| split_substation_based | event_balanced             | doy_sin                                     | 73         |
| split_substation_based | event_balanced             | risk_probability                            | 64         |
| split_substation_based | event_balanced             | day_of_year                                 | 61         |
| split_substation_based | event_balanced             | leadtime_prob_3-7d                          | 58         |
| split_substation_based | hard_case_weighted         | risk_score                                  | 123        |
| split_substation_based | hard_case_weighted         | days_since_last_any_event                   | 93         |
| split_substation_based | hard_case_weighted         | leadtime_prob_0-24h                         | 54         |
| split_substation_based | hard_case_weighted         | doy_cos                                     | 42         |
| split_substation_based | hard_case_weighted         | configuration_type__is__sh_with_buffer_tank | 35         |
| split_substation_based | hard_case_weighted         | doy_sin                                     | 34         |
| split_substation_based | hard_case_weighted         | leadtime_prob_3-7d                          | 24         |
| split_substation_based | hard_case_weighted         | days_since_last_task_event                  | 22         |
| split_substation_based | severity_weighted          | risk_score                                  | 164        |
| split_substation_based | severity_weighted          | days_since_last_any_event                   | 106        |
| split_substation_based | severity_weighted          | leadtime_prob_0-24h                         | 62         |
| split_substation_based | severity_weighted          | leadtime_prob_3-7d                          | 55         |
| split_substation_based | severity_weighted          | doy_cos                                     | 49         |
| split_substation_based | severity_weighted          | doy_sin                                     | 47         |
| split_substation_based | severity_weighted          | configuration_type__is__sh_with_buffer_tank | 27         |
| split_substation_based | severity_weighted          | p_hc1_return_temperature__mean              | 26         |
| split_substation_based | substation_balanced        | risk_score                                  | 148        |
| split_substation_based | substation_balanced        | days_since_last_any_event                   | 89         |
| split_substation_based | substation_balanced        | leadtime_prob_0-24h                         | 65         |
| split_substation_based | substation_balanced        | doy_sin                                     | 57         |
| split_substation_based | substation_balanced        | leadtime_prob_3-7d                          | 51         |
| split_substation_based | substation_balanced        | configuration_type__is__sh_with_buffer_tank | 46         |
| split_substation_based | substation_balanced        | doy_cos                                     | 41         |
| split_substation_based | substation_balanced        | p_hc1_return_temperature__mean              | 32         |
| split_time_based       | baseline_no_weight         | risk_score                                  | 75         |
| split_time_based       | baseline_no_weight         | leadtime_prob_0-24h                         | 42         |
| split_time_based       | baseline_no_weight         | doy_cos                                     | 29         |
| split_time_based       | baseline_no_weight         | configuration_type__is__sh_with_buffer_tank | 20         |
| split_time_based       | baseline_no_weight         | days_since_last_any_event                   | 19         |
| split_time_based       | baseline_no_weight         | risk_probability                            | 17         |
| split_time_based       | baseline_no_weight         | leadtime_prob_1-3d                          | 16         |
| split_time_based       | baseline_no_weight         | leadtime_prob_3-7d                          | 15         |
| split_time_based       | combined_context_resampled | days_since_last_any_event                   | 496        |
| split_time_based       | combined_context_resampled | risk_score                                  | 373        |
| split_time_based       | combined_context_resampled | day_of_year                                 | 336        |
| split_time_based       | combined_context_resampled | leadtime_prob_0-24h                         | 264        |
| split_time_based       | combined_context_resampled | doy_sin                                     | 261        |
| split_time_based       | combined_context_resampled | doy_cos                                     | 176        |
| split_time_based       | combined_context_resampled | predicted_lead_time_confidence              | 168        |
| split_time_based       | combined_context_resampled | leadtime_prob_3-7d                          | 164        |
| split_time_based       | combined_context_weighted  | risk_score                                  | 147        |
| split_time_based       | combined_context_weighted  | leadtime_prob_0-24h                         | 72         |
| split_time_based       | combined_context_weighted  | day_of_year                                 | 56         |
| split_time_based       | combined_context_weighted  | days_since_last_any_event                   | 43         |
| split_time_based       | combined_context_weighted  | risk_probability                            | 28         |
| split_time_based       | combined_context_weighted  | leadtime_prob_1-3d                          | 25         |
| split_time_based       | combined_context_weighted  | doy_sin                                     | 22         |
| split_time_based       | combined_context_weighted  | predicted_lead_time_confidence              | 21         |
| split_time_based       | event_balanced             | risk_score                                  | 69         |
| split_time_based       | event_balanced             | leadtime_prob_0-24h                         | 41         |
| split_time_based       | event_balanced             | doy_cos                                     | 25         |
| split_time_based       | event_balanced             | leadtime_prob_1-3d                          | 18         |
| split_time_based       | event_balanced             | risk_probability                            | 16         |
| split_time_based       | event_balanced             | configuration_type__is__sh_with_buffer_tank | 15         |
| split_time_based       | event_balanced             | days_since_last_any_event                   | 15         |
| split_time_based       | event_balanced             | p_net_meter_energy__first                   | 11         |
| split_time_based       | hard_case_weighted         | risk_score                                  | 53         |
| split_time_based       | hard_case_weighted         | leadtime_prob_0-24h                         | 33         |
| split_time_based       | hard_case_weighted         | days_since_last_any_event                   | 23         |
| split_time_based       | hard_case_weighted         | configuration_type__is__sh_with_buffer_tank | 22         |
| split_time_based       | hard_case_weighted         | doy_cos                                     | 21         |
| split_time_based       | hard_case_weighted         | p_net_meter_energy__mean                    | 12         |
| split_time_based       | hard_case_weighted         | day_of_year                                 | 12         |
| split_time_based       | hard_case_weighted         | risk_probability                            | 9          |
| split_time_based       | severity_weighted          | days_since_last_any_event                   | 404        |
| split_time_based       | severity_weighted          | risk_score                                  | 367        |
| split_time_based       | severity_weighted          | day_of_year                                 | 208        |
| split_time_based       | severity_weighted          | leadtime_prob_0-24h                         | 204        |
| split_time_based       | severity_weighted          | doy_sin                                     | 167        |
| split_time_based       | severity_weighted          | predicted_lead_time_confidence              | 145        |
| split_time_based       | severity_weighted          | leadtime_prob_3-7d                          | 124        |
| split_time_based       | severity_weighted          | p_net_supply_temperature__std               | 114        |
| split_time_based       | substation_balanced        | risk_score                                  | 68         |
| split_time_based       | substation_balanced        | days_since_last_any_event                   | 32         |
| split_time_based       | substation_balanced        | leadtime_prob_0-24h                         | 32         |
| split_time_based       | substation_balanced        | doy_cos                                     | 15         |
| split_time_based       | substation_balanced        | leadtime_prob_3-7d                          | 13         |
| split_time_based       | substation_balanced        | p_net_meter_energy__first                   | 11         |
| split_time_based       | substation_balanced        | risk_probability                            | 9          |
| split_time_based       | substation_balanced        | s_dhw_supply_temperature__max               | 8          |

## 판정 기준

룰베이스보다 좋아졌다고 보려면 최소한 `split_substation_based_holdout`에서 F1과 NDCG@R을 동시에 넘거나, recall 개선을 위해 감수한 false positive 증가가 운영적으로 납득 가능해야 한다.

## 산출물

- report: `report/priority_model_comparison/sampled_lgbm_priority_report.md`
- metrics: `report/priority_model_comparison/sampled_lgbm_priority_metrics.csv`
- selection: `report/priority_model_comparison/sampled_lgbm_priority_selection.csv`
- feature importance: `report/priority_model_comparison/sampled_lgbm_priority_feature_importance.csv`
- predictions: `report/priority_model_comparison/sampled_lgbm_priority_predictions.csv`
- diagnostics: `report/priority_model_comparison/sampled_lgbm_priority_weight_diagnostics.csv`
- models: `report/priority_model_comparison/models/sampled_lgbm_priority.joblib`
