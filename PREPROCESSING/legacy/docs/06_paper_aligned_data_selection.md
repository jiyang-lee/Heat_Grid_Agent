# 06-P1. paper-aligned data selection 문서

이 문서는 `PREPROCESSING/legacy/osj/06_paper_aligned_data_selection.ipynb`의 목적과 산출물 기준을 정리한다.

## 목적

- 논문 기준에 맞는 normal event / fault event 선택 규칙 고정
- 학습용 정상 행동 구간과 평가용 event 구간 분리
- report time 해석 기준과 exclusion 규칙 문서화

## 핵심 원칙

- Autoencoder 학습에는 정상 행동 구간만 사용한다.
- `faults.csv`는 실제 고장 onset이 아니라 report time 기준으로 해석한다.
- 평가는 window 분류보다 event-wise detection 기준으로 정리한다.
- 최근 disturbance / maintenance 영향 구간은 학습 제외 또는 별도 표기한다.

## 예상 입력

```text
data/processed/label_alignment/fault_alignment.csv
data/processed/label_alignment/normal_alignment.csv
data/processed/label_alignment/disturbance_alignment.csv
data/processed/ml_features/trainable_windows.csv
data/processed/ml_windows/ml_window_dataset.csv
```

현재 확인한 입력 상태:

- `fault_alignment.csv`: 73개 event, 전부 `is_usable == True`
- `normal_alignment.csv`: 65개 event, 전부 `is_usable == True`
- `disturbance_alignment.csv`: 328개 row 중 311개 usable
- `trainable_windows.csv`: `normal 1800`, `pre_fault 755`

현재 06-P1에서 바로 써야 할 핵심 컬럼:

```text
fault_alignment:
  manufacturer
  event_id
  substation_id
  fault_label
  report_date
  window_start
  window_end

normal_alignment:
  manufacturer
  event_id
  substation_id
  window_start
  window_end

trainable_windows / ml_window_dataset:
  manufacturer
  substation_id
  window_start
  window_end
  label
  fault_event_id
  disturbance_count
  maintenance_related
  configuration_type
  split_time_based
```

## 06-P1에서 고정할 선택 규칙

1. normal behaviour 학습 구간은 `normal_alignment` 중심으로 먼저 고정한다.
2. report / disturbance 영향 구간과 겹치는 normal window는 학습에서 제외 후보로 둔다.
3. fault event 평가는 `fault_alignment.event_id` 단위로 관리한다.
4. split은 row가 아니라 event 단위로 재확인한다.
5. `configuration_type`은 alignment 원본이 아니라 window 테이블에서 보강한다.
6. Autoencoder 학습에서는 `data_quality_issue`, `use_for_supervised_training == False`, `normal_reference_outlier`, `maintenance_related`, `disturbance_count > 0`를 제외한다.
7. event evaluation에서는 `train` event만 제외하고, validation / holdout normal hard case는 남긴다. 즉 `normal_reference_outlier` normal도 평가에서는 유지한다.

## 예상 출력

```text
data/processed/paper_aligned/normal_behaviour_training_windows.csv
data/processed/paper_aligned/event_evaluation_windows.csv
data/processed/paper_aligned/paper_aligned_data_selection_audit.csv
data/processed/paper_aligned/paper_aligned_data_selection_metadata.json
```

현재 생성된 결과 요약:

```text
usable normal events: 65
usable fault events: 73
usable disturbance rows: 311

normal_behaviour_training_windows row_count: 1818
selected_for_autoencoder_train: 1216
selected_for_autoencoder_validation: 269
selected_for_autoencoder_fit total: 1485
selected_for_normal_event_holdout: 286

event_evaluation_windows row_count: 2633
selected_for_event_eval total: 854
selected_for_event_tuning: 446
selected_for_event_holdout: 408
selected_for_event_eval normal: 584
selected_for_event_eval fault: 270
```

평가 유지 원칙:

- validation / holdout normal event는 가능한 원분포를 유지한다.
- 따라서 학습에서 제외된 `normal_reference_outlier` normal window도 event evaluation에는 남긴다.
- 이 결정은 false alarm을 숨기지 않기 위한 것이다.

## 다음 단계 연결

이 단계 결과는 `06_paper_aligned_autoencoder.ipynb`에서 normal behaviour model 학습 입력으로 사용한다.
