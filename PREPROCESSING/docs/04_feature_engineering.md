# 04. 피처 엔지니어링 및 모델 입력 컬럼 확정

이 문서는 `PREPROCESSING/hsj/04_feature_engineering.ipynb`의 목적, 판단 기준, 산출물을 정리한다.

중요한 원칙은 다음과 같다.

- `00`부터 `03`까지의 노트북과 문서는 수정하지 않는다.
- `04`는 `03` 산출물인 `data/processed/ml_windows/ml_window_dataset.csv`만 읽는다.
- Isolation Forest 입력 후보는 넘겨받은 모델 handoff의 195개 feature 계약을 상한으로 고정한다.
- `04`에서는 새로운 feature를 추가로 만들지 않는다.
- risk와 leadtime용 feature 수는 현재 03 산출물에 실제 존재하는 컬럼 기준으로 조정한다.
- 어떤 컬럼을 선택했고, 어떤 컬럼을 제외했는지 리포트로 남긴다.

## 1. 입력 데이터

기본 입력 파일은 다음과 같다.

```text
data/processed/ml_windows/ml_window_dataset.csv
```

모델 handoff metadata는 다음 위치 중 존재하는 경로를 사용한다.

```text
data/models/heatgrid_ml_models_2026-06-25/
_zip_read/model_handoff/heatgrid_ml_models_2026-06-25/
```

현재 로컬 확인 기준으로 03 산출물은 다음 구조를 가진다.

```text
row_count: 3270
column_count: 252
label normal: 1818
label pre_fault: 815
label unlabeled: 637
```

## 2. 모델별 feature 선택 기준

### 2.1 Isolation Forest

넘겨받은 `baseline_model_metadata.json`에는 Isolation Forest 입력 feature가 195개로 정의되어 있다.

04에서는 이 195개를 절대 초과하지 않는다. 현재 03 산출물에 실제로 존재하는 컬럼만 선택한다.

현재 확인 결과는 다음과 같다.

```text
handoff 계약 feature: 195개
03 산출물에 존재하는 feature: 151개
03 산출물에 없는 feature: 44개
```

따라서 04의 Isolation Forest feature set은 151개로 시작한다.

이렇게 설정한 이유는 다음과 같다.

- 기존 모델 계약을 최대한 따른다.
- 03 산출물에 없는 컬럼을 억지로 생성하지 않는다.
- 사용자가 지정한 “195개보다 늘리지 않는다”는 조건을 지킨다.
- 누락 컬럼은 후속 개선 대상이지, 04에서 임의로 보간하거나 새로 만드는 대상이 아니다.

### 2.2 Risk LightGBM

넘겨받은 `risk_model_metadata.json`에는 risk 모델 입력 feature가 189개로 정의되어 있다.

현재 03 산출물에 실제로 존재하는 risk feature는 144개다.

```text
handoff 계약 feature: 189개
03 산출물에 존재하는 feature: 144개
03 산출물에 없는 feature: 45개
```

04에서는 risk feature를 144개로 조정한다.

이렇게 설정한 이유는 다음과 같다.

- 현재 03 산출물 기준으로 바로 학습 가능한 컬럼만 남긴다.
- `anomaly_score`처럼 05 Isolation Forest 이후에 생성될 컬럼은 04에서 만들지 않는다.
- risk 학습 시점에는 05 산출물을 결합해 `anomaly_score`를 추가할 수 있으므로, 04에서는 “현재 사용 가능한 base risk feature”를 먼저 고정한다.
- 기존 risk metadata에서 제외한 고위험 leakage/불안정 feature 판단을 존중한다.

### 2.3 Leadtime LightGBM

넘겨받은 `leadtime_bucket_model_promoted_metadata.json`에는 leadtime 모델 입력 feature가 221개로 정의되어 있다.

현재 03 산출물에 실제로 존재하는 leadtime feature는 144개다.

```text
handoff 계약 feature: 221개
03 산출물에 존재하는 feature: 144개
03 산출물에 없는 feature: 77개
```

04에서는 leadtime feature를 144개로 조정한다.

이렇게 설정한 이유는 다음과 같다.

- 04에서는 추가 파생 feature를 만들지 않기로 했기 때문이다.
- 기존 leadtime 계약에는 `risk_probability`, `risk_score`, lag, delta, rolling 계열 feature가 포함되어 있다.
- 이 컬럼들은 05/06 이후 결과 또는 timeflow feature 생성 단계와 관련이 있으므로 04에서 임의 생성하지 않는다.
- 현재 단계에서는 03 산출물에서 검증 가능한 feature만 고정하고, leadtime 전용 확장은 06에서 별도 판단하는 편이 책임 경계가 명확하다.

## 3. 제외 기준

다음 계열은 모델 입력 feature에서 제외한다.

- 정답 또는 라벨: `label`, `fault_label`, `fault_event_id`, `estimated_lead_time_hours`
- split/control: `split_*`, `use_for_supervised_training`, `window_source_type`
- 식별자 및 시간 범위: `source_file`, `window_start`, `window_end`
- 설명용 텍스트: `main_missing_sensors`, `main_changed_sensors`
- normal 기준 판정 보조: `normal_reference_*`
- 모델 결과 컬럼: `risk_*`, `predicted_lead_time_*`, `leadtime_prob_*`, `priority_*`

단, `anomaly_score`, `risk_score`, `risk_probability`처럼 후속 모델 metadata에 명시된 모델 결과 컬럼은 해당 모델 학습 단계에서만 별도 결합 대상으로 본다.

## 4. 산출물

04 노트북은 다음 파일들을 생성한다.

```text
data/processed/ml_features/trainable_windows.csv
data/processed/ml_features/feature_columns.csv
data/processed/ml_features/metadata_columns.csv
data/processed/ml_features/feature_selection_report.csv
data/processed/ml_features/feature_family_summary.csv
data/processed/ml_features/label_distribution.csv
data/processed/ml_features/missing_handoff_features.csv
```

`data/processed/`는 `.gitignore` 대상이므로 이 산출물은 Git에 올리지 않고 재생성 가능한 결과로 둔다.

## 5. 다음 단계 연결

05 Isolation Forest는 `feature_columns.csv`에서 `anomaly_feature == True`인 컬럼만 사용한다.

06 Risk LightGBM은 `risk_feature == True`인 컬럼을 base feature로 사용한다. 이후 05에서 생성한 `anomaly_score`를 결합해 risk 모델 입력을 완성한다.

06 Leadtime LightGBM은 `leadtime_feature == True`인 컬럼을 base feature로 사용한다. risk 결과와 timeflow 계열 feature를 추가할지 여부는 06에서 별도 실험 기준으로 판단한다.

## 6. 이번 04 단계의 결론

이번 04 단계는 “feature를 많이 만드는 단계”가 아니라 “현재 03 산출물이 handoff 모델 계약과 얼마나 맞는지 확인하고, 바로 학습 가능한 입력 컬럼을 고정하는 단계”로 둔다.

이 방향이 현재 프로젝트에 가장 효율적인 이유는 다음과 같다.

- 03까지의 결과를 보존한다.
- 기존 모델 handoff 계약을 최대한 재사용한다.
- Isolation Forest 입력 수가 195개를 넘지 않는다.
- 없는 컬럼을 임의 생성하지 않아 재현성이 높다.
- risk와 leadtime은 현재 데이터에 맞는 축소 feature set으로 시작한 뒤, 05/06 단계에서 필요한 결과 컬럼을 결합할 수 있다.
