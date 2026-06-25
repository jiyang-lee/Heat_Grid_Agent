# 06 risk weighting experiment

## 목적

feature를 더 바꾸지 않고도

```text
1-3d pre_fault
+ FN 집중 그룹
```

에 가중치를 주면 recall과 false negative를 개선할 수 있는지 본 실험이다.

## 실행 파일

```text
PREPROCESSING/osj/06_risk_weighting_experiment.py
```

## 출력 파일

```text
data/processed/ml_risk/lgbm_risk_weighting_experiment.csv
data/processed/ml_risk/lgbm_risk_weighting_experiment_holdout.csv
data/processed/ml_risk/lgbm_risk_weighting_false_negative_summary.csv
```

## 비교 variant

```text
baseline_no_weight
leadtime_1_3d_x1_5
leadtime_1_3d_x2
group_x1_5
group_x2
leadtime_1_3d_x1_5_plus_group_x1_5
leadtime_1_3d_x2_plus_group_x1_5
```

## 핵심 결과

### overall holdout calibrated

```text
baseline_no_weight
precision 0.3750
recall    0.2791
f1        0.3200
fpr       0.1869
fn        62
fn_1_3d   37

leadtime_1_3d_x2_plus_group_x1_5
precision 0.4400
recall    0.5116
f1        0.4731
fpr       0.2617
fn        42
fn_1_3d   25
```

해석:

- weighting만으로도 FN은 꽤 줄어든다.
- 특히 `1-3d FN`이 크게 줄어든다.
- 하지만 FPR이 많이 올라간다.

### overall holdout base

최고 F1:

```text
leadtime_1_3d_x2_plus_group_x1_5
f1   0.5025
fpr  0.2944
fn   36
fn_1_3d 23
```

즉 weighting은 확실히 recall/FN 쪽에는 먹힌다.

## 현재 공식 calibrated 본과 비교

현재 공식 운영본:

```text
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449
```

이번 weighting 최고 후보:

```text
precision 0.4400
recall    0.5116
f1        0.4731
fpr       0.2617
```

## 결론

이번 실험은 아래를 확인해줬다.

1. `1-3d`와 FN 집중 그룹에 sample weighting을 주면 recall은 실제로 올라간다.
2. FN과 `1-3d FN`은 꽤 줄어든다.
3. 하지만 그 대가로 FPR이 너무 커진다.

즉 weighting은

```text
보조 조정 수단으로는 의미가 있지만
지금 상태로 메인 공식본을 교체할 정도는 아니다.
```

## 의미

이 실험은 target/weighting 방향이 완전히 틀린 게 아니라는 걸 보여준다.

하지만 진짜 승격까지 가려면

```text
weighting 단독
```

이 아니라

```text
label 재설계
+ feature 표현 개선
+ calibration 재조정
```

이 같이 가야 한다.
