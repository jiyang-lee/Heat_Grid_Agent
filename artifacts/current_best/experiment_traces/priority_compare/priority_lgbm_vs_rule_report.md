# Priority 모델 비교 리포트

## 요약

- 비교 데이터는 현재 공식 룰베이스 산출물 `data/processed/ml_priority/priority_engine_scores_tuned.csv`를 기준으로 만들었다.
- 비교 행 수는 `2362`개이며 split 분포는 train `1652`, validation `344`, holdout `366`이다.
- 실제 버킷 분포는 normal `1726`, 3-7d `69`, 1-3d `356`, 0-24h `211`이다.
- 팀원 산출물은 두 패키지가 맞다. 하나는 priority 회귀 단독 패키지이고, 다른 하나는 anomaly/risk/leadtime 예측 체인과 priority 회귀를 합친 통합 패키지다.
- 다만 두 패키지 안의 `lightgbm_priority_model.joblib`은 SHA256 기준 동일 파일이다: `True`.
- 두 LGBM 패키지의 예측 점수 최대 절대 차이는 `0.000000`이다.
- 전체 데이터 기준 MAE는 LGBM이 Rule-based보다 `1.0699` 낮지만, holdout 기준 MAE는 LGBM이 `5.6005` 더 높다.
- holdout Top-10 graded NDCG는 LGBM이 Rule-based 대비 `-0.0556` 낮다.
- holdout high/urgent 액션 기준 precision은 Rule-based `0.8837`, LGBM `0.8333`이고, recall은 Rule-based `0.7103`, LGBM `0.3271`이다.

## 해석

- LGBM priority 모델은 train 구간에서는 Rule-based보다 낮은 MAE/RMSE를 보이지만, validation과 holdout에서는 성능이 떨어진다. 현재 공식 데이터 기준으로는 일반화가 약한 후보로 보는 것이 맞다.
- Rule-based는 risk level, risk probability, leadtime, anomaly, history adjustment를 사람이 해석 가능한 방식으로 더한 운영 엔진이다. holdout에서 회귀 지표, 순위 지표, high/urgent recall이 모두 LGBM보다 안정적이다.
- LGBM은 high/urgent 판단을 더 보수적으로 한다. 전체 기준 precision과 specificity는 높지만, holdout recall이 크게 낮아 실제 3일 이내 장애 리드타임을 많이 놓친다.
- 팀원 산출물은 패키지 기준으로 두 개가 맞다. `priority-only`는 LGBM 회귀만 넘기는 형태이고, `prediction+priority`는 anomaly/risk/leadtime 예측 모델까지 같이 넘기는 통합 형태다.
- 하지만 두 패키지의 최종 priority 회귀 estimator는 같은 파일이다. 따라서 이 리포트의 Rule-based vs LGBM priority score 비교에서는 두 패키지 간 priority 결과 차이가 없다.
- 통합 패키지에 들어 있는 anomaly/risk/leadtime 모델은 현재 `model_handoff/heatgrid_ml_models_2026-06-25`의 공식 모델과 SHA256 기준 동일하다. 즉 통합 패키지의 차별점은 upstream 모델 자체가 새롭다는 점이 아니라, 예측 체인을 함께 포장했다는 점이다.
- LGBM 메타데이터에는 자체 평가에서 LGBM이 rule baseline을 이겼다고 기록되어 있지만, 현재 저장소에는 그 기준 파일인 `data/processed/ml_model_chain/model_chain_output.csv`가 없다. 이 리포트는 학습 재현이 아니라 현재 공식 룰베이스 산출물 위에서의 재스코어링 비교다.
- 운영 채택 관점에서는 LGBM으로 교체하지 않는 것이 맞다. Rule-based `priority_engine_v2_threshold48`을 공식 유지하고, LGBM은 보수적 shadow score나 추가 검토용 ranking 후보로만 붙이는 것이 안전하다.

## 패키지 구조 확인

| package_key                                    | package_role                              | contains_anomaly_model | contains_risk_model | contains_leadtime_model | contains_priority_lgbm | priority_lgbm_same_as_other_package | upstream_models_match_official_handoff |
| ---------------------------------------------- | ----------------------------------------- | ---------------------- | ------------------- | ----------------------- | ---------------------- | ----------------------------------- | -------------------------------------- |
| heatgrid_priority_model_2026-06-26             | priority regression only                  | False                  | False               | False                   | True                   | True                                | not_applicable                         |
| heatgrid_prediction_priority_models_2026-06-26 | prediction chain plus priority regression | True                   | True                | True                    | True                   | True                                | True                                   |

## Priority 회귀 파일 확인

| model_key              | model_version        | model_type    | best_iteration | n_train_metadata | n_holdout_metadata | sha256                                                           |
| ---------------------- | -------------------- | ------------- | -------------- | ---------------- | ------------------ | ---------------------------------------------------------------- |
| lgbm_priority_only     | priority_v3_lgbm_reg | LGBMRegressor | 384            | 2509             | 837                | 2c4640f199f5baa744abbb07891056e9c158f6304ab31a848e5f8e62a7bc8bfa |
| lgbm_prediction_bundle | priority_v3_lgbm_reg | LGBMRegressor | 384            | 2509             | 837                | 2c4640f199f5baa744abbb07891056e9c158f6304ab31a848e5f8e62a7bc8bfa |

## 회귀/상관 지표

| split   | model                      | n    | mae     | rmse    | r2     | pearson | spearman |
| ------- | -------------------------- | ---- | ------- | ------- | ------ | ------- | -------- |
| all     | Rule-based v2_threshold48  | 2362 | 12.5513 | 17.8680 | 0.7312 | 0.8711  | 0.7523   |
| all     | LGBM priority-only package | 2362 | 11.4814 | 19.6552 | 0.6748 | 0.8240  | 0.6938   |
| holdout | Rule-based v2_threshold48  | 366  | 20.5625 | 26.5861 | 0.4852 | 0.7165  | 0.6854   |
| holdout | LGBM priority-only package | 366  | 26.1631 | 32.6741 | 0.2224 | 0.4877  | 0.4302   |

## High/Urgent 운영 액션 지표

`predicted high/urgent`를 `실제 3일 이내 장애 리드타임(0-24h 또는 1-3d)` 포착으로 평가했다.

| split   | model                      | level_accuracy | level_macro_f1 | action_precision | action_recall | action_f1 | action_specificity | action_rate |
| ------- | -------------------------- | -------------- | -------------- | ---------------- | ------------- | --------- | ------------------ | ----------- |
| all     | Rule-based v2_threshold48  | 0.8345         | 0.5139         | 0.8725           | 0.8571        | 0.8648    | 0.9604             | 0.2358      |
| all     | LGBM priority-only package | 0.7786         | 0.6418         | 0.9462           | 0.6825        | 0.7930    | 0.9877             | 0.1732      |
| holdout | Rule-based v2_threshold48  | 0.6913         | 0.4177         | 0.8837           | 0.7103        | 0.7876    | 0.9614             | 0.2350      |
| holdout | LGBM priority-only package | 0.3689         | 0.3079         | 0.8333           | 0.3271        | 0.4698    | 0.9730             | 0.1148      |

## Holdout Top-K Ranking 지표

`pre_fault` 전체를 relevant로 보고, NDCG는 normal=0, 3-7d=0.33, 1-3d=0.66, 0-24h=1.0의 graded relevance로 계산했다.

| split   | model                      | k_label | pre_fault_count | precision_pre_fault | recall_pre_fault | ndcg_graded |
| ------- | -------------------------- | ------- | --------------- | ------------------- | ---------------- | ----------- |
| holdout | Rule-based v2_threshold48  | 10      | 115             | 1.0000              | 0.0870           | 1.0000      |
| holdout | Rule-based v2_threshold48  | 20      | 115             | 1.0000              | 0.1739           | 0.9014      |
| holdout | Rule-based v2_threshold48  | 50      | 115             | 1.0000              | 0.4348           | 0.8446      |
| holdout | Rule-based v2_threshold48  | 100     | 115             | 0.8400              | 0.7304           | 0.8279      |
| holdout | Rule-based v2_threshold48  | R       | 115             | 0.7304              | 0.7304           | 0.7805      |
| holdout | LGBM priority-only package | 10      | 115             | 1.0000              | 0.0870           | 0.9444      |
| holdout | LGBM priority-only package | 20      | 115             | 0.9000              | 0.1565           | 0.7984      |
| holdout | LGBM priority-only package | 50      | 115             | 0.8200              | 0.3565           | 0.7280      |
| holdout | LGBM priority-only package | 100     | 115             | 0.5700              | 0.4957           | 0.6201      |
| holdout | LGBM priority-only package | R       | 115             | 0.5130              | 0.5130           | 0.5976      |

## 산출물

- Plotly HTML: `report/priority_model_comparison/priority_lgbm_vs_rule_plotly.html`
- 비교 데이터: `report/priority_model_comparison/priority_lgbm_vs_rule_dataset.csv`
- 회귀 지표: `report/priority_model_comparison/priority_lgbm_vs_rule_regression_metrics.csv`
- 운영 액션 지표: `report/priority_model_comparison/priority_lgbm_vs_rule_classification_metrics.csv`
- Top-K 지표: `report/priority_model_comparison/priority_lgbm_vs_rule_topk_metrics.csv`
