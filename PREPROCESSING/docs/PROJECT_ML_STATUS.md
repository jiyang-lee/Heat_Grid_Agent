# HeatGrid ML 현재 상태

이 문서는 현재 프로젝트에서 공식으로 유지하는 ML 구조와 실험 판단을 요약한다.

## 공식 결론

현재 구조는 아래 방향으로 유지한다.

```text
Isolation Forest
-> LightGBM risk
-> LightGBM leadtime
-> rule-based Priority Engine v2_threshold48
-> Agent handoff
```

이 구조는 고장 확정 모델이 아니라 설비실 점검 우선순위를 만들기 위한 위험 신호 생성 체계다.

## 공식 산출물

### 05 Isolation Forest

- 역할: 정상 패턴과 다른 이상징후 탐지
- 주요 출력: `anomaly_score`
- 공식 기준: anomaly score 연속값을 downstream risk/priority에 사용
- 주의: anomaly label 자체를 고장으로 해석하지 않는다.

### 06 Risk LightGBM

- 역할: 고장신고 전 위험구간과 유사한 패턴 판단
- 주요 출력: `risk_score`, `risk_probability`, `risk_level_calibrated`
- 공식 holdout 성능:

```text
F1        0.5466
Recall    0.5116
FPR       0.1449
ROC-AUC   0.7628
```

### 06 Leadtime LightGBM

- 역할: 신고 기준 pseudo leadtime bucket 추정
- 주요 출력: `predicted_lead_time_bucket`, `predicted_lead_time_confidence`, bucket probabilities
- 공식 holdout 성능:

```text
Accuracy  0.6512
Macro F1  0.4405
Top2 Acc  0.9651
```

주의:

- 이 값은 실제 고장 발생 시점 예측이 아니다.
- `faults.csv`의 신고 시점을 기준으로 만든 pseudo leadtime이다.
- `3-7d` 버킷은 샘플 수가 적어 현재 신뢰도가 낮다.

### 07 Priority Engine

- 역할: 설비실별 점검 우선순위 산출
- 공식 버전: `priority_engine_v2_threshold48`
- 주요 출력: `priority_score`, `priority_level`, `priority_reason`, `engine_version`
- 공식 holdout 성능:

```text
Precision 1.0000
Recall    0.5116
F1        0.6769
FPR       0.0000
TP        44
FP        0
FN        42
TN        214
```

## 최근 실험 판단

### Isolation Forest threshold/hyperparameter

threshold quantile을 낮추면 recall과 F1은 올라갈 수 있다.
하지만 FPR이 같이 증가할 수 있으므로 공식 05를 바로 교체하지 않는다.

현재 Priority Engine은 binary anomaly label보다 `anomaly_score` 연속값을 사용한다.

### Risk hyperparameter tuning

validation 기준으로는 개선 후보가 있었지만 holdout에서 공식 risk 모델보다 약했다.
따라서 공식 risk 모델은 유지한다.

### Leadtime tuning

일부 tuning 후보가 macro F1을 소폭 개선했지만, `3-7d` 버킷 혼동 문제가 남아 있다.
현재 공식 3-bucket 체인은 유지하고, Agent에서는 confidence와 top2 정보를 함께 쓰는 방식이 더 안전하다.

### Priority LGBM regression

회귀모델 후보는 일부 지표가 좋아 보였지만, leadtime 출력이 pre-fault 샘플 중심으로 존재하는 구조 때문에 leakage risk가 있다.
따라서 v3로 승격하지 않는다.

## 현재 한계

- 실제 고장 발생 시점 라벨이 아니라 신고 시점 라벨을 사용한다.
- leadtime은 실제 고장까지 남은 시간이 아니라 신고 기준 pseudo leadtime이다.
- holdout group drift가 존재하므로 risk 모델의 false positive/false negative를 계속 감사해야 한다.
- `3-7d` leadtime bucket은 현재 데이터 양과 분포상 신뢰도가 낮다.

## 다음 개선 후보

1. Risk false negative audit을 기준으로 놓친 위험구간의 공통 feature를 재검토한다.
2. Leadtime은 `0-24h`, `1-3d`, `3-7d`를 유지하되 `3-7d` confidence 하한과 표시 방식을 별도 관리한다.
3. Isolation Forest는 threshold quantile 후보를 공식 교체하지 말고 anomaly score scaling 또는 보조 feature로만 우선 검토한다.
4. Priority Engine은 `threshold48`을 공식 유지하고, 추후 변경 시 FPR `0.0000` 또는 운영 허용 FPR 기준을 먼저 정한다.
