# 06 manufacturer 2 / SH false positive audit

## 목적

현재 holdout에서 오탐이 가장 많이 남는 그룹인 `manufacturer 2 / SH`를 따로 떼어 본다.

질문은 단순하다.

```text
정상인데 high로 찍힌 샘플에서
어떤 feature가 risk score를 밀어올렸는가?
```

## 실행 파일

```text
PREPROCESSING/osj/06_manufacturer2_sh_fp_audit.py
```

## 출력 파일

```text
data/processed/ml_risk/manufacturer2_sh_fp_feature_contributions.csv
data/processed/ml_risk/manufacturer2_sh_fp_feature_summary.csv
data/processed/ml_risk/manufacturer2_sh_fp_vs_tn_feature_compare.csv
```

## 비교 대상

- 대상 그룹: `manufacturer 2 + configuration_type SH`
- split: `holdout`
- 정상 샘플만 비교
- 기준:
  - false positive: `risk_probability >= 0.44`
  - true negative: `risk_probability < 0.44`

현재 개수:

```text
false positives: 11
true negatives: 42
```

## 핵심 결과

오탐 샘플에서 정상 저위험 샘플보다 더 강하게 점수를 올린 feature는 아래 순서다.

```text
days_since_last_any_event
days_since_last_task_event
p_net_return_temperature__max
network_temperature_gap__mean
doy_sin
day_of_year
p_net_supply_temperature__mean
doy_cos
p_net_supply_temperature__max
```

가장 중요한 해석은 다음과 같다.

### 1. event-context 계열이 오탐 점수를 강하게 밀어올린다

특히:

```text
days_since_last_any_event
days_since_last_task_event
```

이 둘은 오탐 샘플 11건 전부에서 양의 기여를 보였다.

즉 이 그룹에서는

```text
과거 이벤트와의 거리 정보가
정상 샘플에도 과하게 위험 신호로 해석될 가능성
```

이 있다.

### 2. 열적 상태 관련 feature도 같이 점수를 올린다

특히:

```text
p_net_return_temperature__max
network_temperature_gap__mean
p_net_supply_temperature__mean
p_net_supply_temperature__max
```

이 feature들은 event-context와 같이 등장한다.

즉 오탐은 보통 단일 원인보다

```text
이벤트 거리 + 열적 편차
```

조합으로 발생한다.

### 3. 실제 오탐은 substation 11에 더 집중된다

```text
substation 11: 8건
substation 59: 3건
```

또한 평균 위험도도 `substation 11`이 더 높다.

즉 `manufacturer 2 / SH` 전체 문제이기도 하지만,
실제로는 `substation 11`이 더 강한 잔여 오탐 구간이다.

## 샘플 패턴

대표 오탐 샘플에서는 아래 조합이 반복된다.

```text
days_since_last_any_event
network_temperature_gap__mean
days_since_last_task_event
p_net_return_temperature__max 또는 p_net_return_temperature__mean
doy_sin
p_net_supply_temperature__mean
```

즉 모델은 이 샘플을

```text
최근 이벤트 이력 문맥 + 열적 편차가 겹친 위험 패턴
```

으로 읽고 있다.

## 결론

삭제/유지 판단을 쉽게 정리하면:

### 바로 삭제 후보

아직 없음.

이유:

- 오탐을 올리는 feature가 보이긴 하지만
- 같은 feature가 전체 holdout에서는 유효 신호이기도 하다.

### 우선 재검토 후보

```text
days_since_last_any_event
days_since_last_task_event
network_temperature_gap__mean
p_net_supply_temperature__mean
p_net_supply_temperature__max
```

### 더 안전한 다음 조치

전역 삭제보다 아래가 더 적절하다.

```text
1. manufacturer 2 / SH 전용 calibration 검토
2. substation 11 전용 residual audit
3. event-context feature clipping / bucketization 검토
4. thermal gap feature를 절대값 대신 관계식/정규화 방식으로 재설계 검토
```

## 현재 실무 판단

지금 단계에서 가장 맞는 해석은 이것이다.

```text
오탐의 주범은 단일 feature 하나가 아니라
event-context와 thermal-gap 계열의 결합이다.
```

따라서 다음 수순은

```text
전역 삭제
```

가 아니라

```text
group-aware 보정 또는 feature 표현 변경
```

이 더 맞다.
