# HeatGrid Priority Regression Model Handoff

이 패키지는 proto 완성본 기준 우선순위 LGBM 회귀모델만 담은 전달 ZIP이다.

## 구조

```text
heatgrid_priority_model_2026-06-26/
├─ priority/
│  ├─ lightgbm_priority_model.joblib
│  └─ priority_model_metadata.json
├─ MANIFEST.json
└─ README.md
```

## 입력

`model_chain_output.csv`의 7개 feature를 사용한다. 순서는 `priority/priority_model_metadata.json`의 `feature_order`를 따른다.

- anomaly_score
- risk_probability
- risk_score
- leadtime_prob_0-24h
- leadtime_prob_1-3d
- leadtime_prob_3-7d
- predicted_lead_time_confidence

## 출력

모델 출력은 0~100 priority score이며, proto에서는 `16.5 / 49.5 / 83.0` 경계로 low/medium/high/urgent를 밴딩한다.

## 학습 기준

full PreDist supervised 3346 window를 raw -> preprocessing -> IF/risk/leadtime 모델 체인까지 통과시킨 `model_chain_output.csv` 기준으로 학습했다.
