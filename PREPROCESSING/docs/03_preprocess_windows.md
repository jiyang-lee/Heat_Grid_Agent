# 03. ML 학습용 윈도우 데이터셋 생성 문서

이 문서는 `PREPROCESSING/osj/03_preprocess_windows.ipynb`의 목적과 산출물 기준을 HeatGrid Agent 프로젝트 관점에서 정리한다.

03번 노트북은 원본 운영 시계열을 그대로 모델에 넣지 않고, 일정 시간 구간 단위의 ML 입력 데이터셋으로 변환한다.
초기 기본값은 전체 운영 기간이 아니라 `fault`, `normal`, `disturbance`와 연결되는 학습 후보 구간만 처리한다.

## 프로젝트 관점의 목적

HeatGrid Agent에서 ML은 우선순위를 직접 결정하지 않는다.
ML은 Agent가 판단할 수 있도록 다음 정보를 제공해야 한다.

- 어느 기계실의 데이터인지
- 어느 시간 구간의 상태인지
- 정상 후보인지, 고장 전 위험 후보인지
- 고장신고까지 얼마나 남았는지
- 데이터 품질이 믿을 만한지
- 어떤 센서 변화가 컸는지

따라서 03번의 역할은 모델 학습이 아니라, 이후 모델이 학습할 수 있는 기본 입력 테이블을 만드는 것이다.

```text
raw 운영 시계열
+ 02번 라벨 정렬 결과
+ 설비 구성 정보
→ 기계실별 시간 구간 단위 ML 학습 후보 데이터셋
```

## 입력 데이터

03번은 다음 파일을 사용한다.

```text
data/processed/label_alignment/operational_coverage.csv
data/processed/label_alignment/fault_alignment.csv
data/processed/label_alignment/normal_alignment.csv
data/processed/label_alignment/disturbance_alignment.csv
data/raw_data/predist_v2/manufacturer */operational_data/substation_*.csv
data/raw_data/predist_v2/manufacturer */configuration_types.csv
```

`data/processed/label_alignment/`의 파일은 02번 노트북에서 생성한 결과다.

## 처리 범위

03번의 기본 설정은 다음과 같다.

```text
KEEP_ONLY_RELEVANT_WINDOWS = True
```

이 설정에서는 전체 운영 기간의 모든 윈도우를 만들지 않는다.
대신 다음 구간만 처리한다.

- fault_alignment에서 사용 가능한 fault 후보 구간
- normal_alignment에서 사용 가능한 normal 후보 구간
- disturbance_alignment의 정비/작업 시점 주변 구간

이렇게 하는 이유는 다음과 같다.

- 전체 운영 기간을 모두 윈도우로 만들면 라벨 없는 행이 매우 많아진다.
- 초기 supervised baseline에는 fault/normal 후보 구간이 더 중요하다.
- 03번 노트북이 너무 무거워지면 초보자가 흐름을 확인하기 어렵다.
- 불필요한 장기 미라벨 구간보다 Agent 설명에 연결되는 후보 구간을 먼저 정리하는 것이 낫다.

나중에 운영 전체 기간에 대해 추론용 윈도우가 필요하면 다음처럼 바꿔 실행하면 된다.

```python
KEEP_ONLY_RELEVANT_WINDOWS = False
```

즉, 03번 함수 구조는 전체 기간 생성도 가능하지만, 기본 산출물은 학습 후보 구간 중심으로 둔다.

## 윈도우 기준

초기 기준은 다음과 같다.

```text
window_size = 6시간
step_size = 6시간
```

겹치는 윈도우를 쓰지 않는 이유는 다음과 같다.

- 결과 확인이 쉽다.
- train/test 간 유사 구간 누수를 줄일 수 있다.
- baseline 모델을 만들기 전에 라벨과 데이터 품질을 검토하기 좋다.

나중에 모델 성능을 비교할 때는 3시간, 12시간, 24시간 윈도우를 추가 실험할 수 있다.

## 결측치 처리 기준

결측치는 모델 입력 계산을 위해 보간하지만, 결측 정보 자체는 버리지 않는다.

03번에서는 각 윈도우마다 다음 값을 남긴다.

```text
missing_count
missing_rate
센서별 missing_count
센서별 missing_rate
```

값 계산에는 다음 순서의 간단한 보간을 사용한다.

```text
window 내부 forward fill
window 내부 backward fill
window 내부 median fill
```

결측을 완전히 없애는 것이 목적이 아니다.
Agent가 결과를 해석할 때 “이 구간은 데이터 품질이 낮다”는 정보를 알 수 있도록 결측률을 feature로 남기는 것이 핵심이다.

서로 다른 fault, normal, disturbance 구간 사이의 값은 보간에 사용하지 않는다.
이 기준을 지키지 않으면 미래 구간 값이나 다른 이벤트 구간 값이 현재 window feature에 섞일 수 있다.

## 이상치 처리 기준

03번에서는 이상치를 삭제하지 않는다.

고장 전 위험 징후는 통계적으로 보면 이상치처럼 보일 수 있기 때문이다.
예를 들어 공급온도 급변, 유량 급감, 환수온도 상승은 제거 대상이 아니라 모델이 봐야 할 신호다.

대신 다음 정보를 flag로 남긴다.

```text
sensor_error_candidate_count
extreme_change_count
data_quality_issue
```

물리적으로 말이 안 되는 값은 센서 오류 후보로 표시한다.

예:

```text
온도 < -50
온도 > 150
유량 < 0
열량 < 0
누적 에너지/체적 값 감소
```

## 생성 feature

03번에서는 전체 컬럼을 무작정 모두 쓰지 않고, HeatGrid Agent 설명에 필요한 핵심 센서 중심으로 feature를 만든다.
기존에는 숫자로 해석되지 않는 control mode/status 계열 컬럼을 기본 feature에서 제외했지만,
현재 보강안에서는 해당 컬럼이 존재하면 윈도우별 대표 상태와 변화 횟수를 별도 context 컬럼으로 남긴다.

각 센서별 기본 feature:

```text
mean
min
max
std
first
last
delta
missing_count
missing_rate
```

주요 파생 feature:

```text
hc1_supply_temperature_gap
dhw_supply_temperature_gap
network_temperature_gap
```

의미는 다음과 같다.

- `hc1_supply_temperature_gap`: 난방 공급온도와 설정온도의 차이
- `dhw_supply_temperature_gap`: 급탕 공급온도와 설정온도의 차이
- `network_temperature_gap`: 네트워크 공급온도와 환수온도의 차이

Agent에게는 단순히 “온도가 높다”보다 “설정값 대비 실제 공급온도 편차가 커졌다”는 정보가 더 유용하다.

시간 문맥 feature:

```text
hour_of_day
day_of_week
day_of_year
month
is_weekend
is_heating_season
season_bucket
hour_sin
hour_cos
dow_sin
dow_cos
doy_sin
doy_cos
```

이 feature들은 6시간 윈도우 요약만으로는 놓치기 쉬운 시간대/요일/계절 레짐 차이를 직접 반영한다.
LightGBM이 순환 구조를 잘못 해석하지 않도록 시간대와 요일은 `sin/cos`로 함께 남긴다.

이벤트/안정화 문맥 feature:

```text
days_since_last_fault_event
days_since_last_task_event
days_since_last_any_event
post_fault_stabilization
post_task_stabilization
recent_regime_change_flag
normal_reference_group
```

여기서 `post_*_stabilization`은 fault 또는 작업 직후 일정 기간을 “정상 후보”와 분리하기 위한 보조 기준이다.
현재 기본 안정화 구간은 14일이다.

## 라벨 부여 기준

라벨은 다음 순서로 붙인다.

```text
fault 구간과 겹치고 window_end <= report_date
그리고 고장신고 전 7일 이내
→ label = pre_fault

normal event 구간과 겹침
→ label = normal

둘 다 아니면
→ label = unlabeled
```

`disturbance`는 고장 라벨로 직접 쓰지 않는다.
대신 다음 보조 컬럼으로 남긴다.

```text
maintenance_related
disturbance_count
```

정비나 작업 이력은 실제 이상징후인지, 작업 영향인지 Agent가 해석할 때 필요한 배경 정보다.

`unlabeled`는 정상 라벨이 아니다.
03번에서는 이 의미를 명확히 하기 위해 다음 컬럼을 함께 만든다.

```text
window_source_type
use_for_supervised_training
```

`use_for_supervised_training`은 `normal`, `pre_fault`일 때만 `True`다.
따라서 05번 baseline 모델 학습에서는 기본적으로 `unlabeled`를 제외해야 한다.

## normal 기준 보강 메모

06번 audit 결과 기준으로 현재 normal 정의는 라벨 오염보다는 분포 차이 문제가 더 크다.
특히 holdout의 `manufacturer 2` normal이 train normal과 다른 패턴을 보여 false positive가 집중됐다.

따라서 03번에서 다음 기준을 재검토할 필요가 있다.

- normal 후보를 제조사와 `configuration_type` 기준으로 따로 요약해 분포 차이를 먼저 본다
- normal 후보를 `season_bucket`까지 포함한 regime 단위로 분리해 본다
- normal event와 겹치더라도 온도 drift가 큰 구간은 별도 표식으로 남긴다
- fault / task 직후 안정화 구간은 normal 후보에서 바로 쓰지 않는다
- 운영 전체에서 무작위 normal을 넓게 섞기보다, 설비 구성과 시기 차이가 과도한 normal 구간은 학습 기준에서 분리할 수 있게 한다

즉, 다음 보강의 핵심은 normal 행을 더 많이 넣는 것이 아니라, 어떤 normal을 기준 분포로 볼지 명시적으로 기록하는 것이다.

03번 보강 산출물:

```text
data/processed/ml_windows/normal_profile_by_group.csv
data/processed/ml_windows/normal_reference_drift_by_group.csv
```

이 파일들은 `split_regime_based + manufacturer + configuration_type + season_bucket` 기준 normal profile과
train 대비 holdout normal drift를 기록한다.

현재 적용한 1차 필터 규칙:

- 대상 group: `manufacturer 2` + `configuration_type == SH`
- 기준 feature:
  - `p_net_return_temperature__std`
  - `p_net_return_temperature__mean`
  - `s_hc1_supply_temperature_setpoint__std`
- train normal 기준 IQR 바깥인 feature 수가 `2개 이상`이면
  - `normal_reference_outlier = True`
  - `use_for_supervised_training = False`

이 규칙은 holdout normal 중 일부만 제거하는 1차 방어선이다.
이후에도 holdout normal risk가 높게 남으면 group 분리 또는 기준 재정의가 추가로 필요하다.

## pre_fault lead time 제한

03번의 기본 설정은 다음과 같다.

```text
MAX_PREFAULT_LEAD_HOURS = 168
```

즉, 고장신고 전 7일 이내 구간만 `pre_fault` 학습 후보로 쓴다.

일부 fault는 `Possible anomaly start`가 매우 과거까지 잡혀 있을 수 있다.
이 값을 그대로 쓰면 수개월 전 구간까지 고장 전 위험 라벨이 붙을 수 있고, 초기 모델이 실제 위험 징후가 아니라 장기 계절 패턴이나 일반 운영 패턴을 고장 전 라벨로 학습할 위험이 있다.

7일 기준은 확정값이 아니라 초기 baseline 기준이다.
이후 04~06 단계에서 24시간, 72시간, 168시간 기준을 비교할 수 있다.

## label leakage 방지

고장신고 이후의 정보를 `pre_fault` 학습에 섞으면 안 된다.

그래서 03번에서는 다음 기준을 둔다.

```text
window_end <= report_date
```

이 기준을 만족하지 않는 fault 겹침은 `pre_fault`로 쓰지 않고, `leakage_blocked_fault_count`로 남긴다.
또한 03번에서도 fault interval의 종료 시점을 `report_date` 이전으로 한 번 더 자른다.
02번에서 정리된 라벨을 쓰더라도, 03번이 자체적으로 한 번 더 방어해야 label leakage 가능성을 줄일 수 있다.

## 설비 구성 정보

`configuration_types.csv`에서 다음 정보를 붙인다.

```text
configuration_type
has_dhw
has_buffer_tank
```

같은 센서 변화라도 설비 구성에 따라 Agent의 점검 항목이 달라질 수 있다.

예를 들어 DHW가 있는 기계실과 없는 기계실은 급탕 관련 센서 해석 기준이 다르다.

## holdout 분리

03번에서는 모델 학습 전 단계이지만, 이후 실수를 줄이기 위해 split 컬럼을 미리 만든다.

```text
split_time_based
split_substation_based
split_regime_based
```

값은 다음 중 하나다.

```text
train
validation
holdout
```

초기 모델링에서는 `split_time_based`를 기본으로 사용한다.
`split_substation_based`는 처음 보는 기계실에 대한 일반화 성능을 비교할 때 사용한다.
보강 후에는 `split_regime_based`를 추가로 저장해, normal도 제조사/설비구성/계절 레짐을 기준으로 더 안정적으로 나눌 수 있게 한다.

## 저장 산출물

03번 노트북은 다음 파일을 생성한다.

```text
data/processed/ml_windows/ml_window_dataset.csv
data/processed/ml_windows/normal_profile_by_group.csv
data/processed/ml_windows/normal_reference_drift_by_group.csv
data/processed/ml_windows/window_time_context_profile.csv
```

이 파일은 GitHub에 올리지 않는다.
`data/processed/`는 `.gitignore` 대상이다.

## 다음 단계 연결

03번 결과는 아직 최종 모델 입력이 아니다.

다음 04번에서는 다음 작업을 한다.

- 학습에 사용할 feature 컬럼 선택
- 결측률이 높은 feature 제외
- 제조사 공통 feature와 제조사별 feature 분리
- label 분포 확인
- Agent 설명에 사용할 센서명과 feature명 정리

03번의 핵심은 다음 한 문장으로 정리할 수 있다.

```text
고장 징후를 지우지 않고, Agent가 해석할 수 있는 시간 구간 단위 ML 입력 데이터로 정리한다.
```
