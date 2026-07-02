# PreDist 전처리 샘플 fixture

- 원본 ZIP: `C:\Users\Admin\Downloads\predist_dataset.zip`
- 샘플 대상: manufacturer 1 substation_10, manufacturer 2 substation_24
- sensor_readings 행 수: 300
- fault_events 행 수: 2
- maintenance_events 행 수: 9
- preprocessed_windows 행 수: 10
- preprocessed_windows 컬럼 수: 211
- preprocessing_version: `preprocessed_data_v1`
- `raw/` 아래 4개 CSV만으로 원본 ZIP 없이 전처리 재현이 가능하다.
- 전처리 결과는 `output/preprocessed_windows_sample.csv`에 저장한다.
- `configuration_types.csv`가 없어 `configuration_type="missing"` fallback을 사용한다.
