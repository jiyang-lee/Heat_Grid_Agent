# 06 false negative deep audit

## 목적

기존 false negative audit를 더 세분화해서 아래를 확인했다.

1. 어떤 그룹에서 놓치는가
2. `low`와 `medium` 중 어디에 많이 남는가
3. 어떤 leadtime 구간에서 많이 놓치는가
4. threshold 근처에서 걸려 있는가
5. true positive와 비교할 때 어떤 수치 차이가 큰가

## 실행 파일

```text
PREPROCESSING/osj/06_false_negative_deep_audit.py
```

## 출력 파일

```text
data/processed/ml_risk/holdout_false_negative_group_summary.csv
data/processed/ml_risk/holdout_false_negative_level_summary.csv
data/processed/ml_risk/holdout_false_negative_score_band_summary.csv
data/processed/ml_risk/holdout_false_negative_leadtime_summary.csv
data/processed/ml_risk/holdout_false_negative_threshold_window.csv
data/processed/ml_risk/holdout_false_negative_group_feature_diff.csv
```

## 핵심 결과

### 1. false negative는 특정 그룹에 몰린다

상위 그룹:

```text
manufacturer 2 | SH with buffer tank : 19
manufacturer 2 | SH + DHW            : 8
manufacturer 1 | SH + DHW            : 7
manufacturer 2 | SH                  : 6
```

즉 지금 놓치는 구간은 전역적으로 균일하지 않고,
특정 configuration 성격에 몰린다.

### 2. low와 medium이 같이 문제지만, medium FN도 많다

```text
medium : 23
low    : 19
```

즉 단순히 `0.22` 아래만 문제인 게 아니라
이미 `medium`까지는 올라왔는데 `high`를 못 넘는 경우도 많다.

### 3. leadtime 기준으로는 1-3d가 가장 많이 놓친다

```text
1-3d  : 28
6-24h : 10
0-6h  : 4
```

즉 calibration 이후에도 가장 많이 놓치는 구간은
즉시 직전보다 `중간 단계 pre_fault`다.

### 4. score band 기준으로도 중간 구간이 핵심이다

```text
below_medium      : 19
medium_0.22_0.30 : 10
medium_0.30_0.36 : 5
medium_0.36_0.44 : 6
```

해석:

- 아예 낮게 깔리는 FN도 있다.
- 하지만 `0.22 ~ 0.44` 사이 medium FN이 합계 21개다.
- 즉 이 문제는 단순 threshold 한 번 조정으로 끝나지 않는다.

### 5. true positive 대비 false negative는 thermal 수치가 더 높다

상위 차이:

```text
network_temperature_gap__mean
p_net_return_temperature__mean
p_net_return_temperature__max
s_dhw_upper_storage_temperature__last
s_dhw_upper_storage_temperature__max
p_net_supply_temperature__mean
p_net_supply_temperature__max
```

요약하면:

```text
놓친 pre_fault는
열적 절대값이 더 높은데도
risk로 충분히 밀어올리지 못하는 경우가 있다.
```

## 현재 해석

이번 deep audit 기준으로 다음 해석이 가능하다.

### 1. 핵심 문제는 중간 pre_fault 구간 표현 부족

`1-3d` 구간 FN이 가장 많고,
점수도 `0.22~0.44` 사이에 많이 분포한다.

즉 모델이 이미 위험 신호는 일부 받았지만,
그걸 `high` 쪽으로 충분히 밀지 못하고 있다.

### 2. configuration별 thermal 표현 차이가 더 중요하다

특히 아래 쪽이 우선 타깃이다.

```text
manufacturer 2 | SH with buffer tank
manufacturer 2 | SH + DHW
manufacturer 1 | SH + DHW
```

즉 다음 실험은 전체 전역 튜닝보다
이 그룹들에 먹히는 thermal relation / event-context 재표현을 봐야 한다.

### 3. 다음 우선순위는 false positive보다 false negative 보강

지금 공식본은 FPR을 많이 줄였지만,
그 대가로 `중간 pre_fault` recall 손실이 일부 남아 있다.

## 바로 다음 작업

이번 audit 이후 바로 이어질 작업은 아래가 맞다.

```text
1. event-context 상태형 재표현 실험
2. thermal relation/group feature 재실험
3. 위 두 실험을 false negative 중심으로 다시 평가
```

즉 지금 다음 06 개선의 핵심은

```text
1-3d 구간 pre_fault를
high 쪽으로 더 잘 끌어올리는 표현
```

을 만드는 것이다.
