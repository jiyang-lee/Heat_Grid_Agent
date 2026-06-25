# 2026-06-23 ML 전처리 작업 기록

이 문서는 새 Codex 세션이 현재 작업 맥락을 바로 이해할 수 있도록 작성한 작업 기록이다.

프로젝트 이름은 **HeatGrid Agent**다.
사용자는 ML 파트를 담당하며, 목표는 PreDist raw data를 전처리하고 ML 학습 결과를 이후 Agent 제작자에게 넘길 수 있는 형태로 만드는 것이다.

## 현재 작업 범위

현재까지 작업한 범위는 `PREPROCESSING/osj` 아래 00~03번 노트북이다.

```text
00_load_dataset.ipynb
→ raw 데이터 다운로드

01_raw_inspection.ipynb
→ raw 운영 CSV 구조, 컬럼, 결측 상태 확인

02_label_alignment.ipynb
→ fault / normal / disturbance 라벨 구간을 운영 시계열 시간 범위와 정렬

03_preprocess_windows.ipynb
→ ML 학습용 6시간 window dataset 생성
```

관련 문서는 `PREPROCESSING/docs` 아래에 정리되어 있다.

```text
00_load_dataset.md
01_raw_inspection.md
02_label_alignment.md
03_preprocess_windows.md
```

## 중요한 프로젝트 기준

ML은 우선순위를 직접 산출하지 않는다.

ML 파트는 Agent가 판단할 수 있도록 다음 자료를 제공하는 역할이다.

- 기계실 ID
- 시간 구간
- 정상 후보 / 고장 전 위험 후보
- 고장신고까지 남은 시간
- 센서별 요약 feature
- 결측 및 데이터 품질 정보
- 정비/작업 영향 여부
- 설비 구성 정보

Agent는 이 자료를 받아서 위험 가능성, 점검 필요성, 원인 후보, 작업지시서 초안을 종합 판단한다.

## Git / 데이터 관리 기준

raw data와 processed data는 GitHub에 올리지 않는다.

현재 `.gitignore`에는 다음 계열이 포함되어야 한다.

```text
data/raw_data/
data/_downloads/
data/processed/
```

즉, 아래 산출물은 로컬에서만 생성되고 커밋 대상이 아니다.

```text
data/processed/label_alignment/*.csv
data/processed/ml_windows/ml_window_dataset.csv
```

## 오늘 수정한 핵심 내용

### 1. 00번 노트북

`PREPROCESSING/osj/00_load_dataset.ipynb`

확인/수정 내용:

- `urllib.request` 사용에 필요한 import를 보완했다.
- `requests`는 `uv add requests`로 의존성에 추가되어 있다.
- Zenodo / Mendeley ZIP 다운로드 후 `data/raw_data` 아래에 압축을 푸는 구조다.

주의:

- 00번은 외부 네트워크 다운로드가 포함되어 있으므로 매번 자동 실행하지 않아도 된다.
- raw data는 GitHub에 올리지 않는다.

### 2. 01번 노트북

`PREPROCESSING/osj/01_raw_inspection.ipynb`

작업 내용:

- PreDist v2의 모든 운영 CSV를 대상으로 구조를 확인하도록 정리했다.
- 불필요한 시각화는 제거했다.
- 결측은 그래프가 아니라 표로 간단히 본다.
- 사용자에게 보이는 표 제목과 컬럼명은 한글로 표시한다.
- Python 변수명/함수명은 영어만 사용한다.

주요 확인 항목:

- 제조사별 운영 CSV 파일 수
- 파일별 행 수 / 컬럼 수
- 컬럼별 결측 행 수 / 결측률
- manufacturer 1 / manufacturer 2의 컬럼 차이
- label 파일들의 기본 구조

### 3. 02번 노트북

`PREPROCESSING/osj/02_label_alignment.ipynb`

작업 내용:

- `faults.csv`, `normal_events.csv`, `disturbances.csv`를 운영 시계열 시간 범위와 정렬한다.
- 산출물은 다음 위치에 저장한다.

```text
data/processed/label_alignment/
```

생성 파일:

```text
operational_coverage.csv
fault_alignment.csv
normal_alignment.csv
disturbance_alignment.csv
```

중요 수정:

- fault fallback window가 `Report date` 이후로 넘어가던 문제를 수정했다.
- 현재 fault window는 항상 `Report date` 이전으로 끝난다.
- `Possible anomaly start`가 없거나 이상하면 fallback은 다음처럼 잡는다.

```text
Report date - 3일 ~ Report date
```

검증 결과:

```text
fault_alignment 행 수: 73
usable: 73
window_start > report_date: 0
window_end > report_date: 0
missing window date: 0
```

이 수정은 중요하다.
고장신고 이후 데이터가 fault 학습 후보에 들어가면 실제 운영 시점에서는 알 수 없는 정보를 모델이 학습하게 되므로 label leakage가 발생한다.

### 4. 03번 노트북

`PREPROCESSING/osj/03_preprocess_windows.ipynb`

역할:

```text
raw 운영 시계열
+ 02번 라벨 정렬 결과
+ 설비 구성 정보
→ 6시간 단위 ML 학습 후보 window dataset
```

산출물:

```text
data/processed/ml_windows/ml_window_dataset.csv
```

기본 설정:

```text
WINDOW_SIZE = 6시간
WINDOW_FREQ = 6시간
KEEP_ONLY_RELEVANT_WINDOWS = True
MAX_PREFAULT_LEAD_HOURS = 168
DISTURBANCE_CONTEXT_HOURS = 6
```

`KEEP_ONLY_RELEVANT_WINDOWS = True`이므로 전체 운영 기간을 모두 자르지 않는다.
기본적으로 fault, normal, disturbance와 관련 있는 후보 구간만 window로 만든다.
전체 운영 기간 추론용 데이터가 필요하면 `False`로 바꿀 수 있다.

## 03번에서 반영한 중요한 방어 로직

### fault interval clamp

03번에서도 fault 구간을 한 번 더 `Report date` 이전으로 자른다.
02번이 이미 정리되어 있어도, 03번에서 다시 방어한다.

기준:

```text
fault_interval_start = max(window_start, report_date - 168시간)
fault_interval_end = min(window_end, report_date)
```

### window 내부 보간

결측 보간은 같은 window 안에서만 수행한다.

현재 기준:

```text
window 내부 forward fill
window 내부 backward fill
window 내부 median fill
```

이유:

- 서로 다른 fault / normal / disturbance 구간의 값이 섞이면 안 된다.
- 미래 구간 값이 과거 window feature에 들어가면 안 된다.

### 이상치 처리

이상치는 삭제하지 않는다.

고장 전 위험 징후가 통계적으로 이상치처럼 보일 수 있기 때문이다.
대신 다음 feature로 남긴다.

```text
sensor_error_candidate_count
extreme_change_count
data_quality_issue
```

### all-null feature 제거

숫자로 변환하면 전부 NaN이 되던 control mode/status 계열 컬럼은 03번 기본 feature에서 제외했다.
나중에 필요하면 04번 이후 categorical feature로 따로 다룬다.

제외한 예:

```text
s_hc1_control_unit_mode
s_dhw_control_unit_mode
s_hc1_heating_pump_status_setpoint
```

### unlabeled 학습 제외

`unlabeled`는 정상 라벨이 아니다.

03번에서 다음 컬럼을 추가했다.

```text
window_source_type
use_for_supervised_training
```

지도학습에는 기본적으로 다음 조건만 사용한다.

```text
use_for_supervised_training == True
```

현재 `normal`, `pre_fault`만 `True`다.
`unlabeled`, `disturbance_context`, `post_fault_blocked`는 학습 제외다.

## 03번 최종 검증 결과

`data/processed/ml_windows/ml_window_dataset.csv`

```text
행 수: 3,270
컬럼 수: 195
```

라벨 분포:

```text
normal: 1,818
pre_fault: 815
unlabeled: 637
```

source type 분포:

```text
normal_context: 1,818
pre_fault_context: 815
related_unlabeled: 363
disturbance_context: 201
post_fault_blocked: 73
```

지도학습 사용 여부:

```text
True: 2,633
False: 637
```

품질 검증:

```text
중복 window key: 0
all-null 컬럼: 0
pre_fault lead time 오류: 0
unlabeled인데 지도학습 사용 True: 0
normal/pre_fault인데 지도학습 사용 False: 0
post_fault_blocked인데 지도학습 사용 True: 0
```

lead time:

```text
min: 0.066667시간
median: 37.25시간
max: 167.533333시간
```

## 현재 남은 낮은 수준의 주의점

### 1. time based split에서 fault event 1개가 갈라짐

`split_time_based` 기준에서 fault event 1개가 두 split에 걸쳐 있다.

확인된 케이스:

```text
manufacturer 1 / substation 28 / fault_event_id 47
```

이건 지금 당장 03번을 막는 문제는 아니다.
하지만 05번 모델 평가에서 event 단위 holdout을 엄격하게 보려면 `event_group_id` 기반 split을 추가하는 것이 좋다.

### 2. data_quality_issue가 있는 supervised 행이 있음

현재 supervised 대상 중 일부는 `data_quality_issue=True`다.

분포:

```text
normal: 18
pre_fault: 60
```

04번에서 다음 기준을 정해야 한다.

```text
기본 학습셋은 data_quality_issue == False만 사용할지
품질 이슈가 있는 행도 포함해서 성능 비교할지
```

추천:

```text
기본 학습: data_quality_issue == False
비교 실험: data_quality_issue 포함
```

## 다음 작업

다음은 04번이다.

권장 파일명:

```text
PREPROCESSING/osj/04_feature_selection.ipynb
PREPROCESSING/docs/04_feature_selection.md
```

04번에서 할 일:

1. `ml_window_dataset.csv` 불러오기
2. `use_for_supervised_training == True`만 기본 학습 후보로 필터링
3. `data_quality_issue` 포함/제외 기준 검토
4. label 분포 확인
5. 학습에 쓰지 말아야 할 메타 컬럼 분리
6. 모델 입력 feature 컬럼 후보 확정
7. 결측률 높은 feature 제거 기준 정리
8. manufacturer 공통 feature / 제조사별 feature 분리 여부 판단
9. 최종 feature list 저장

04번 산출물 후보:

```text
data/processed/ml_features/trainable_windows.csv
data/processed/ml_features/feature_columns.csv
data/processed/ml_features/metadata_columns.csv
```

## 새 Codex 세션에 전달할 핵심 지시

새 세션에서는 바로 코드를 바꾸기 전에 다음을 먼저 확인하면 된다.

```text
1. PREPROCESSING/osj/02_label_alignment.ipynb
2. PREPROCESSING/osj/03_preprocess_windows.ipynb
3. PREPROCESSING/docs/02_label_alignment.md
4. PREPROCESSING/docs/03_preprocess_windows.md
5. data/processed/ml_windows/ml_window_dataset.csv
```

확인 명령 예:

```powershell
uv run jupyter nbconvert --to notebook --execute PREPROCESSING\osj\02_label_alignment.ipynb --output 02_label_alignment.executed.ipynb --output-dir PREPROCESSING\osj
uv run jupyter nbconvert --to notebook --execute PREPROCESSING\osj\03_preprocess_windows.ipynb --output 03_preprocess_windows.executed.ipynb --output-dir PREPROCESSING\osj
```

검증용 `.executed.ipynb`는 커밋하지 않는다.
실행 후 삭제해도 된다.

## 현재 결론

00~03 흐름은 다음 단계로 넘어갈 수 있는 상태다.

가장 중요한 label leakage와 보간 누수 가능성은 02~03에서 방어했다.
다음 단계는 04번에서 실제 학습에 사용할 feature와 학습 대상 행을 정리하는 것이다.
