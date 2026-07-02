# 07 Priority LightGBM Regression Candidate Summary

## 목적

Rule-based Priority v2_threshold48을 기준으로, LightGBM 회귀모델이 우선순위 점수를 더 잘 정렬할 수 있는지 실험했다.

## Validation 기준 선택 threshold

- `v2_threshold48_fixed`: `48.0`
- `risk_gated_urgency_x8_fixed`: `52.0`
- `lgbm_guarded_fpr0`: `74.0`
- `lgbm_guarded_fpr1pct`: `74.0`
- `lgbm_guarded_fpr5pct`: `74.0`
- `lgbm_leak_diagnostic_fpr0`: `69.0`

## Holdout 비교

- `v3_lgbm_leak_diagnostic_fpr0`: threshold `69.0`, F1 `1.0000`, Recall `1.0000`, Precision `1.0000`, FPR `0.0000`, TP `86`, FP `0`
- `v2_threshold48`: threshold `48.0`, F1 `0.6769`, Recall `0.5116`, Precision `1.0000`, FPR `0.0000`, TP `44`, FP `0`
- `risk_gated_urgency_x8`: threshold `52.0`, F1 `0.6769`, Recall `0.5116`, Precision `1.0000`, FPR `0.0000`, TP `44`, FP `0`
- `v3_lgbm_guarded_fpr0`: threshold `74.0`, F1 `0.3925`, Recall `0.2442`, Precision `1.0000`, FPR `0.0000`, TP `21`, FP `0`
- `v3_lgbm_guarded_fpr1pct`: threshold `74.0`, F1 `0.3925`, Recall `0.2442`, Precision `1.0000`, FPR `0.0000`, TP `21`, FP `0`
- `v3_lgbm_guarded_fpr5pct`: threshold `74.0`, F1 `0.3925`, Recall `0.2442`, Precision `1.0000`, FPR `0.0000`, TP `21`, FP `0`

## 해석

- v3 후보는 실제 출동 우선순위 정답이 없어서 pre_fault와 leadtime bucket으로 만든 proxy target을 학습한다.
- 현재 leadtime 예측 컬럼은 normal에는 모두 결측, pre_fault에는 모두 존재하므로 그대로 쓰면 라벨 누수가 된다.
- 따라서 승격 검토 대상은 `v3_lgbm_guarded_*` 결과이며, `v3_lgbm_leak_diagnostic_*`는 누수 확인용 기록이다.
- 따라서 회귀 MAE보다 holdout F1, Recall, FPR, TopK 포착률을 중심으로 봐야 한다.
- v2_threshold48보다 FPR을 유지하면서 F1/Recall/TopK가 개선될 때만 v3 승격을 검토한다.
