# Raw 기반 LGBM Priority Regression vs Rule-base 실험

## 목적

팀원 `priority_with_readme`의 LGBM priority regression을 실제 raw operational data에서 출발한 inference 결과에 붙여, 현재 rule-based priority engine과 비교했다.

실험 흐름:

```text
data/raw_data/predist_v2
-> inference_handoff raw windowing
-> anomaly/risk/leadtime upstream score 생성
-> rule-based priority score
-> 팀원 LGBM priority head 적용
-> trainable_windows label과 key join 후 평가
```

## 사용한 파일

- raw scoring output: `report/priority_model_comparison/raw_inference_scores.csv`
- team LGBM model: `lgbm_priority_model/.../priority/lightgbm_priority_model.joblib`
- labels for evaluation: `data/processed/ml_features/trainable_windows.csv`

## 데이터 매칭

- raw inference 전체 rows: `331595`
- label join 가능 rows: `2526`
- label join rate: `0.7618%`
- split_time_based 분포: train `1770`, validation `362`, holdout `394`
- target bucket 분포: normal `1767`, 3-7d `69`, 1-3d `427`, 0-24h `263`

raw inference는 전체 운영 기간의 모든 6시간 window를 만들지만, 성능 평가는 라벨이 있는 window에 대해서만 가능하다.

## 팀원 모델 구조

- model_version: `priority_v3_lgbm_reg`
- model_type: `LGBMRegressor`
- training_basis metadata: `data/processed/ml_model_chain/model_chain_output.csv`

입력 feature:

```text
anomaly_score
risk_probability
risk_score
leadtime_prob_0-24h
leadtime_prob_1-3d
leadtime_prob_3-7d
predicted_lead_time_confidence
```

팀원 LGBM은 raw sensor를 직접 보지 않고, raw에서 upstream 모델을 거쳐 나온 7개 score/probability feature만 사용한다.

## 비교 결과

| split              | model_key | n    | mae     | rmse    | spearman | precision@10 | recall@10 | ndcg@10 | precision@R | recall@R | ndcg@R | precision@100 | recall@100 | ndcg@100 | action_precision | action_recall | action_f1 | action_specificity | action_rate | fp  | fn  |
| ------------------ | --------- | ---- | ------- | ------- | -------- | ------------ | --------- | ------- | ----------- | -------- | ------ | ------------- | ---------- | -------- | ---------------- | ------------- | --------- | ------------------ | ----------- | --- | --- |
| all_labeled        | raw_rule  | 2526 | 22.2219 | 26.6066 | 0.6370   | 1.0000       | 0.0132    | 1.0000  | 0.8221      | 0.8221   | 0.8349 | 1.0000        | 0.1318     | 0.9628   | 0.7957           | 0.7565        | 0.7756    | 0.9270             | 0.2597      | 134 | 168 |
| all_labeled        | team_lgbm | 2526 | 16.9797 | 26.2985 | 0.6382   | 1.0000       | 0.0132    | 1.0000  | 0.7352      | 0.7352   | 0.7650 | 0.9400        | 0.1238     | 0.9284   | 0.8909           | 0.4377        | 0.5870    | 0.9798             | 0.1342      | 37  | 388 |
| split_time_holdout | raw_rule  | 394  | 30.1315 | 35.3939 | 0.4317   | 1.0000       | 0.0752    | 1.0000  | 0.6617      | 0.6617   | 0.7089 | 0.7100        | 0.5338     | 0.7054   | 0.6341           | 0.6240        | 0.6290    | 0.8327             | 0.3122      | 45  | 47  |
| split_time_holdout | team_lgbm | 394  | 26.2543 | 33.9125 | 0.4730   | 0.8000       | 0.0602    | 0.7572  | 0.6015      | 0.6015   | 0.6270 | 0.6400        | 0.4812     | 0.6248   | 0.7105           | 0.2160        | 0.3313    | 0.9591             | 0.0964      | 11  | 98  |
| team_mod3_holdout  | raw_rule  | 548  | 22.4052 | 28.7868 | 0.6637   | 1.0000       | 0.0412    | 1.0000  | 0.8354      | 0.8354   | 0.8555 | 1.0000        | 0.4115     | 0.8763   | 0.8913           | 0.6833        | 0.7736    | 0.9351             | 0.3358      | 20  | 76  |
| team_mod3_holdout  | team_lgbm | 548  | 19.3633 | 30.1489 | 0.7356   | 1.0000       | 0.0412    | 1.0000  | 0.8519      | 0.8519   | 0.8612 | 0.9900        | 0.4074     | 0.8408   | 0.9524           | 0.4167        | 0.5797    | 0.9838             | 0.1916      | 5   | 140 |

## 핵심 판정

- split_time_based holdout 기준 rule MAE `30.1315`, LGBM MAE `26.2543`
- split_time_based holdout 기준 rule NDCG@R `0.7089`, LGBM NDCG@R `0.6270`
- split_time_based holdout 기준 rule high/urgent recall `0.6240`, LGBM high/urgent recall `0.2160`
- split_time_based holdout 기준 rule high/urgent F1 `0.6290`, LGBM high/urgent F1 `0.3313`

현재 raw 기반 inference 결과에 팀원 LGBM head를 붙여도, 공식 운영 holdout 기준에서는 rule-base가 더 안정적이다.

## 해석

1. 팀원 LGBM은 raw 전체를 직접 학습한 모델이 아니다. raw에서 만들어진 anomaly/risk/leadtime score 7개를 다시 섞는 priority head다.
2. rule-base도 같은 upstream score를 쓰지만, risk level, leadtime bucket, history adjustment를 명시적으로 반영한다.
3. raw 전체 window에서는 rule-base가 high/urgent를 더 많이 만들고, LGBM은 더 보수적으로 높은 점수를 준다.
4. 라벨이 있는 holdout 평가에서는 LGBM의 보수성이 recall 손실로 나타난다.
5. 따라서 현재 raw inference chain 기준에서도 LGBM priority regression을 rule-base 대신 운영 공식 모델로 교체할 근거는 부족하다.

## 최종 결론

```text
현재 raw 기반 실험 기준:
rule-base > team LGBM priority regression

운영 권장:
rule-base priority_engine_v2_threshold48 유지
team LGBM은 shadow score 또는 추가 재학습 후보로 유지
```

LGBM이 rule-base를 이기려면 priority head가 7개 upstream score만 쓰는 구조를 넘어, raw/window sensor feature, history feature, rule component score까지 포함한 재학습이 필요하다.
