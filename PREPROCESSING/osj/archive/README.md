# Archive

이 폴더는 공식 실행 흐름에서 제외된 구버전 wrapper 또는 basic 구현을 보관한다.

현재 공식 흐름은 `PREPROCESSING/osj/README.md`의 실행 순서를 따른다.

## 포함 파일

- `06_risk_official_wrapper.py`
  - 과거 risk official wrapper
  - 현재는 `pipeline_scripts/06_risk_calibration.py`를 직접 사용

- `06_leadtime_official_wrapper.py`
  - 과거 leadtime official wrapper
  - 현재는 `pipeline_scripts/06_leadtime_model.py`를 직접 사용

- `07_priority_engine_basic.py`
  - priority engine basic 버전
  - 현재 공식은 tuned 버전인 `pipeline_scripts/07_priority_engine.py`
