# PreDist 전처리 샘플 fixture

- 원본 ZIP: `C:\Users\Admin\Downloads\predist_dataset.zip`
- 샘플링 기준: full PreDist supervised 후보 비율 감사값
- supervised_window_labels 행 수: 300
- label 분포: normal=163, pre_fault=137
- pre_fault bucket 분포: 0-24h=19, 1-3d=39, 3-7d=79
- 라벨 파일은 `output/supervised_window_labels.csv`에 별도로 둔다.
- sensor_readings 행 수: 10800
- fault_events 행 수: 67
- maintenance_events 행 수: 281
- preprocessed_windows 행 수: 300
- preprocessed_windows 컬럼 수: 211
- preprocessing_version: `preprocessed_data_v1`
- `raw/` 아래 4개 CSV만으로 원본 ZIP 없이 전처리 재현이 가능하다.
- 전처리 결과는 `output/preprocessed_windows_sample.csv`에 저장한다.
- `configuration_types.csv`가 없어 `configuration_type="missing"` fallback을 사용한다.
