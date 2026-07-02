# 06 Hyperparameter Tuning Summary

## 실험 원칙

- train split으로만 학습했다.
- validation split으로 하이퍼파라미터를 선택했다.
- holdout split은 최종 비교에만 사용했다.
- 기존 공식 산출물은 덮어쓰지 않았다.

## Isolation Forest

- grid size: `96`
- feature count: `195`
- 공식 holdout F1/Recall/FPR: `0.2267` / `0.1278` / `0.0000`
- 튜닝 holdout F1/Recall/FPR: `0.4615` / `0.3158` / `0.0268`
- 선택 파라미터: n_estimators `300`, max_samples `1.0`, max_features `0.75`, bootstrap `False`, q `0.9`

## Risk LightGBM

- grid size: `432`
- feature count: `189`
- 공식 holdout F1/Recall/FPR/ROC-AUC: `0.5466` / `0.5116` / `0.1449` / `0.7628`
- 튜닝 holdout F1/Recall/FPR/ROC-AUC: `0.3250` / `0.3023` / `0.2243` / `0.5592`
- 선택 candidate_id: `354`

## Leadtime LightGBM

- grid size: `648`
- feature count: `221`
- 공식 holdout accuracy/macro_f1/top2: `0.6512` / `0.4405` / `0.9651`
- 튜닝 holdout accuracy/macro_f1/top2: `0.6744` / `0.4571` / `0.9651`
- 선택 candidate_id: `394`

## 결론

- Risk LightGBM은 튜닝 후보가 공식 모델을 명확히 넘지 못했다.
- Leadtime LightGBM은 튜닝 후보가 macro F1을 개선했다.
- Isolation Forest는 threshold/parameter 튜닝으로 anomaly label 민감도 개선 여지가 있다.
