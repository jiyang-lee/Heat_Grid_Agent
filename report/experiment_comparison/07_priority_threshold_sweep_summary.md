# 07 Priority Threshold Sweep Summary

## 목적

Priority Engine에서 high/urgent 판정 threshold를 현재 52점에서 낮췄을 때, holdout 오탐률(FPR)이 언제 증가하는지 확인했다.

## 핵심 결과

### official_priority_v2

- FPR 0.0000 유지 가능한 최저 threshold: `48.0`
- FPR 0.0000 조건에서 F1 최고 threshold: `49.0`
- 해당 F1/Recall/Precision: `0.6769` / `0.5116` / `1.0000`
- FPR 0.01 이하 허용 시 최저 threshold: `47.5`

### risk_gated_urgency_x8

- FPR 0.0000 유지 가능한 최저 threshold: `48.0`
- FPR 0.0000 조건에서 F1 최고 threshold: `52.0`
- 해당 F1/Recall/Precision: `0.6769` / `0.5116` / `1.0000`
- FPR 0.01 이하 허용 시 최저 threshold: `47.5`

### ungated_urgency_x8

- FPR 0.0000 유지 가능한 최저 threshold: `48.0`
- FPR 0.0000 조건에서 F1 최고 threshold: `48.0`
- 해당 F1/Recall/Precision: `0.6870` / `0.5233` / `1.0000`
- FPR 0.01 이하 허용 시 최저 threshold: `47.5`

## 현재 threshold 52 기준

- `official_priority_v2`: F1 `0.6016`, Recall `0.4302`, Precision `1.0000`, FPR `0.0000`, TP `37`, FP `0`
- `risk_gated_urgency_x8`: F1 `0.6769`, Recall `0.5116`, Precision `1.0000`, FPR `0.0000`, TP `44`, FP `0`
- `ungated_urgency_x8`: F1 `0.6769`, Recall `0.5116`, Precision `1.0000`, FPR `0.0000`, TP `44`, FP `0`

## 해석

- FPR 0.0000을 엄격히 유지하려면 threshold를 무작정 낮출 수 없다.
- threshold를 낮추면 recall은 증가하지만, 특정 지점부터 정상/비위험 구간도 high/urgent로 올라와 FPR이 증가한다.
- 실무 적용 후보는 FPR 0.0000 유지 threshold와 FPR 0.01 이하 threshold를 나눠서 검토하는 것이 적절하다.
