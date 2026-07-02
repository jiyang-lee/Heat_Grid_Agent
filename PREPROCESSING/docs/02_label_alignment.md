# 02. 라벨 구간 정렬 문서

이 문서는 `PREPROCESSING/osj/02_label_alignment.ipynb`의 목적과 출력 기준을 HeatGrid Agent 프로젝트 관점에서 정리한다.

02번 노트북은 라벨 파일의 시간 구간이 실제 운영 시계열 데이터와 맞는지 검증하는 단계다.
아직 학습용 윈도우를 만들지 않는다.
대신 ML이 위험 가능성, lead time, 정상 대비 이상 패턴을 학습할 수 있도록 사용할 수 있는 라벨 구간 후보를 선별한다.

## 프로젝트 관점의 목적

HeatGrid Agent의 ML 산출물은 Agent에게 다음 정보를 넘겨야 한다.

- 어느 기계실에서 위험 가능성이 있는지
- 어느 시간 구간이 위험 후보인지
- 고장 신고까지 얼마나 남았는지, 즉 lead time 후보
- 정상 패턴과 다른 센서 변화가 있었는지
- 정비/작업 이력이 해석에 영향을 줄 수 있는지

이를 위해 02번 단계에서는 fault / normal / disturbance 이벤트를 운영 시계열 시간축에 맞춘다.

## fault 구간 정책

`Possible anomaly start/end`가 모두 있으면 그 구간을 사용한다.
다만 ML 학습 목적의 fault 구간은 고장신고 전 위험 후보를 찾기 위한 것이므로, `Report date`가 있으면 fault window의 종료 시점은 `Report date`로 둔다.

`Possible anomaly start`가 비어 있거나 `Report date` 이후로 잡혀 있으면 `Report date - 3일 ~ Report date`를 fallback window로 만든다.

이유는 단일 timestamp만 검사하면 실제 고장 신고 전 위험 패턴이 존재해도 `no_rows_in_window`로 빠질 수 있기 때문이다.
HeatGrid Agent의 목적은 고장 확정이 아니라 신고 전 위험 가능성과 lead time 후보를 찾는 것이므로, start가 없는 fault는 신고 전 lookback window로 다루는 편이 더 적절하다.

중요한 기준은 다음과 같다.

```text
fault 학습 후보 구간은 Report date 이후로 넘어가지 않는다.
```

고장신고 이후의 데이터가 섞이면 모델이 실제 운영 시점에서는 알 수 없는 정보를 학습할 수 있으므로, 02번에서 먼저 차단한다.

## issue 기준

- `usable`: 운영 데이터와 라벨 구간이 겹치고 실제 row가 있음
- `no_operational_file`: 해당 기계실 운영 CSV가 없음
- `missing_window`: 라벨의 시작/종료 시각을 만들 수 없음
- `out_of_range`: 운영 데이터 범위와 라벨 구간이 겹치지 않음
- `no_rows_in_window`: 시간 범위는 겹치지만 실제 timestamp row가 없음

`is_usable`은 이 구간을 ML 학습/평가 후보로 써도 되는지 판단하는 품질 플래그다.

## 저장 산출물

노트북은 아래 경로에 CSV를 저장한다.

`data/processed/label_alignment/`

저장 파일:

- `operational_coverage.csv`
- `fault_alignment.csv`
- `normal_alignment.csv`
- `disturbance_alignment.csv`

## 다음 단계 연결

다음 단계는 `03_preprocess_windows.ipynb`다.
03번에서는 `is_usable = True`인 라벨 구간을 우선 사용해 학습/평가용 시계열 윈도우를 생성한다.
