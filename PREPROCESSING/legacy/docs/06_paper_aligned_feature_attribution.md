# 06-P4. paper-aligned feature attribution 문서

이 문서는 `PREPROCESSING/legacy/osj/06_paper_aligned_feature_attribution.ipynb`의 목적과 산출물 기준을 정리한다.

## 목적

- reconstruction error 기여 feature 계산
- main abnormal features 생성
- Agent가 읽을 수 있는 설명 필드 초안 정의

## 핵심 원칙

- 설명은 운영자가 이해할 수 있어야 한다.
- 단순 중요도 숫자만 남기지 않고 센서명과 방향성을 함께 남긴다.
- feature attribution 결과는 고장 확정이 아니라 이상 근거다.

## 구현 기준

현재 환경에는 ARCANA가 없으므로, 다음 대체 attribution을 사용한다.

```text
scaled reconstruction squared error
-> row-level normalized contribution
-> detected event의 criticality crossed window에서 평균
-> top feature ranking
```

focus window 규칙:

- 기본: `criticality_crossed == True`인 window
- fallback: crossed window가 없으면 `anomaly_score` 최대 window 1개

## 입력

```text
data/processed/paper_aligned/event_detection_timeline.csv
data/processed/ml_windows/ml_window_dataset.csv
data/processed/ml_features/feature_columns.csv
data/processed/ml_features/imputation_values.csv
data/processed/paper_aligned/models/paper_aligned_autoencoder_model.joblib
data/processed/paper_aligned/models/paper_aligned_autoencoder_scaler.joblib
```

## 출력

```text
data/processed/paper_aligned/feature_attribution_summary.csv
data/processed/paper_aligned/main_abnormal_features.csv
data/processed/paper_aligned/feature_attribution_metadata.json
```

현재 생성 결과:

```text
event-level rows: 44
top5 attribution rows: 220
detected events: 17
non-detected events: 27

focus_rule:
  criticality_crossed_windows: 17
  max_anomaly_score_window: 27
```

설명 랭킹 제외 항목:

```text
row_count
missing_count
missing_rate
max_timestamp_gap_minutes
extreme_change_count
has_dhw
has_buffer_tank
*__missing_count
*__missing_rate
```

이유:

- 모델 입력에는 남겨도 되지만, Agent 설명 상단에 나오면 운영자 해석 품질이 떨어진다.
- 06-P4는 설명 계층만 정리하고 모델 자체는 바꾸지 않는다.

## 다음 단계 연결

이 단계 결과는 `06_paper_aligned_agent_contract.ipynb`에서 `main_abnormal_features`와 `feature_explanation` 필드로 연결한다.
