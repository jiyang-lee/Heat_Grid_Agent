# 06 Hyperparameter Tuning Wide Summary

## 실험 원칙

- train split으로만 학습했다.
- validation split으로 하이퍼파라미터를 선택했다.
- holdout split은 최종 비교에만 사용했다.
- 넓은 범위는 전체 exhaustive grid가 아니라 고정 seed random search로 수행했다.

## Isolation Forest Wide

- sample size: `220`
- validation 선택 holdout F1/Recall/FPR: `0.5538` / `0.4060` / `0.0307`

## Risk LightGBM Wide

- sample size: `320`
- validation 선택 holdout F1/Recall/FPR/ROC-AUC: `0.1560` / `0.1279` / `0.2056` / `0.5275`
- holdout oracle 최고 F1: `0.5455`

## Leadtime LightGBM Wide

- sample size: `320`
- validation 선택 holdout accuracy/macro_f1/top2: `0.6047` / `0.3912` / `0.9651`
- holdout oracle 최고 macro_f1: `0.4849`

## 결론

- Risk는 넓은 튜닝에서도 validation 선택 후보가 holdout 일반화를 안정적으로 개선하는지 확인해야 한다.
- Leadtime은 bucket별 confusion과 함께 승격 여부를 판단한다.
- Isolation Forest는 민감도 개선과 오탐 증가 trade-off가 핵심이다.
