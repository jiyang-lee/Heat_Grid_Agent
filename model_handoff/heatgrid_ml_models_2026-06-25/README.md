# HeatGrid ML Model Handoff

이 폴더는 HeatGrid Copilot의 공식 `PREPROCESSING/osj` flow 기준으로 다음 단계 Agent/서비스 추론에 넘길 학습 파일만 모은 전달 패키지다.

`PREPROCESSING/osj/06_test` 실험 모델, legacy/paper_aligned 모델, 대량 score CSV 산출물은 제외했다.

## 1. 폴더 구조

```text
heatgrid_ml_models_2026-06-25/
├─ anomaly/
│  ├─ standard_scaler.joblib
│  ├─ isolation_forest.joblib
│  └─ baseline_model_metadata.json
├─ risk/
│  ├─ lightgbm_risk_model.joblib
│  ├─ risk_model_group_calibration.json
│  └─ risk_model_metadata.json
├─ leadtime/
│  ├─ lightgbm_leadtime_bucket_model_promoted.joblib
│  └─ leadtime_bucket_model_promoted_metadata.json
├─ priority/
│  └─ priority_engine_tuned_metadata.json
├─ docs/
│  ├─ agent_preprocessed_input_columns.md
│  └─ agent_full_data_contract.md
├─ MANIFEST.json
└─ README.md
```

## 2. 전체 추론 흐름

```text
preprocessed operational base columns
+ context sources
→ feature engineering/windowing
→ Isolation Forest
→ anomaly_score
→ LightGBM Risk
→ risk_probability / risk_level_calibrated
→ LightGBM Leadtime
→ predicted_lead_time_bucket
→ Priority Engine
→ priority_score / priority_level
```

## 3. 입력 데이터 기준

입력 컬럼 계약은 아래 문서를 기준으로 한다.

- `docs/agent_preprocessed_input_columns.md`
- `docs/agent_full_data_contract.md`

요약하면 다음 입력이 필요하다.

- 전처리 후 유지되는 operational base columns 29개
- source metadata: `manufacturer`, `substation_id`, `source_file`
- context source tables:
  - `configuration_types.csv`
  - `faults.csv`
  - `disturbances.csv`
  - `normal_events.csv`

주의: 이 패키지는 모델 파일 묶음이다. raw data, processed feature table, score CSV는 포함하지 않는다.

## 4. Anomaly 모델

파일:

- `anomaly/standard_scaler.joblib`
- `anomaly/isolation_forest.joblib`
- `anomaly/baseline_model_metadata.json`

역할:

- 정상 운전 패턴과 다른 구간을 탐지한다.
- 고장 확정 모델이 아니다.

주요 출력:

- `anomaly_score`
- `anomaly_label`
- `anomaly_threshold`
- `main_abnormal_features`

의미:

- `anomaly_score`: 정상 패턴 대비 얼마나 다른지
- `anomaly_label`: threshold 기준 이상 여부
- `main_abnormal_features`: 이상 판단에 영향을 준 주요 센서/feature 후보

## 5. Risk 모델

파일:

- `risk/lightgbm_risk_model.joblib`
- `risk/risk_model_group_calibration.json`
- `risk/risk_model_metadata.json`

역할:

- Isolation Forest가 잡은 이상징후 또는 feature 패턴이 고장신고 전 위험 패턴과 얼마나 유사한지 판단한다.
- 고장 확정 모델이 아니라 위험 가능성 모델이다.

주요 출력:

- `risk_score`
- `risk_probability`
- `risk_level_calibrated`
- `model_explanation_features`

의미:

- `risk_score`: 고장신고 전 위험 패턴 유사도 점수
- `risk_probability`: 위험 가능성 확률값
- `risk_level_calibrated`: group calibration이 반영된 위험 등급
- `model_explanation_features`: risk 판단에 영향을 준 주요 feature

주의:

- `risk_model_group_calibration.json`은 group별 threshold/calibration 설정이다.
- 최종 운영 해석에는 raw risk score만 쓰지 말고 calibration 결과를 같이 사용한다.

## 6. Leadtime 모델

파일:

- `leadtime/lightgbm_leadtime_bucket_model_promoted.joblib`
- `leadtime/leadtime_bucket_model_promoted_metadata.json`

역할:

- 현재 패턴이 신고 기준 leadtime bucket 중 어디에 가까운지 판단한다.
- 실제 고장 발생 시각을 직접 예측하는 모델이 아니다.
- `faults.csv`의 신고 시점을 기준으로 만든 pseudo leadtime bucket 모델이다.

주요 출력:

- `predicted_lead_time_bucket`
- `predicted_lead_time_confidence`
- `leadtime_prob_0-24h`
- `leadtime_prob_1-3d`
- `leadtime_prob_3-7d`
- `lead_time_bucket_distance`

의미:

- `predicted_lead_time_bucket`: 신고까지 남은 시간 구간 예측
- `predicted_lead_time_confidence`: bucket 예측 확신도
- `leadtime_prob_*`: 각 leadtime bucket 확률
- `lead_time_bucket_distance`: 임박 위험 쪽과의 거리감

## 7. Priority Engine

파일:

- `priority/priority_engine_tuned_metadata.json`

역할:

- anomaly, risk, leadtime, event history를 조합해 설비실별 점검/출동 우선순위를 계산한다.
- `.joblib` 학습 모델이 아니라 rule/score engine 설정 metadata다.

주요 출력:

- `priority_score`
- `priority_level`
- `priority_reason`
- `risk_base_score`
- `risk_probability_component_score`
- `leadtime_component_score`
- `anomaly_component_score`
- `history_adjustment_score`
- `history_adjustment_reason`
- `engine_version`

## 8. Python 로딩 예시

```python
from pathlib import Path
import json
import joblib

ROOT = Path("heatgrid_ml_models_2026-06-25")

scaler = joblib.load(ROOT / "anomaly" / "standard_scaler.joblib")
isolation_forest = joblib.load(ROOT / "anomaly" / "isolation_forest.joblib")

risk_model = joblib.load(ROOT / "risk" / "lightgbm_risk_model.joblib")
risk_metadata = json.loads((ROOT / "risk" / "risk_model_metadata.json").read_text(encoding="utf-8"))
risk_calibration = json.loads((ROOT / "risk" / "risk_model_group_calibration.json").read_text(encoding="utf-8"))

leadtime_model = joblib.load(ROOT / "leadtime" / "lightgbm_leadtime_bucket_model_promoted.joblib")
leadtime_metadata = json.loads((ROOT / "leadtime" / "leadtime_bucket_model_promoted_metadata.json").read_text(encoding="utf-8"))

priority_metadata = json.loads((ROOT / "priority" / "priority_engine_tuned_metadata.json").read_text(encoding="utf-8"))
```

## 9. 추론 구현 시 주의사항

- 모델 입력 feature 순서는 metadata에 기록된 feature 목록과 맞춰야 한다.
- `standard_scaler.joblib`은 Isolation Forest 입력에만 사용한다.
- Risk 모델 결과는 `risk_model_group_calibration.json`을 반영해 해석한다.
- Leadtime 모델은 실제 고장 발생 시각 예측이 아니라 신고 기준 bucket 예측이다.
- Priority Engine은 모델 파일이 아니라 score 계산 규칙이므로, metadata 기준으로 동일한 scoring logic을 구현해야 한다.

## 10. 제외한 파일

아래 파일들은 최종 전달 기준에서 제외했다.

- `PREPROCESSING/osj/06_test` 실험 모델
- `data/processed/ml_risk/models/lightgbm_risk_model_promoted_overall.joblib`
- `data/processed/ml_risk/models/lightgbm_risk_model_promoted_manufacturer2_sh.joblib`
- `data/processed/ml_risk/models/risk_model_promoted_metadata.json`
- `data/processed/ml_leadtime/models/lightgbm_leadtime_bucket_3_model.joblib`
- `data/processed/ml_leadtime/models/leadtime_bucket_3_model_metadata.json`
- `data/processed/paper_aligned/models/*`
- 대량 score CSV 파일

## 11. 무결성 확인

`MANIFEST.json`에 각 파일의 byte size와 SHA256 hash가 들어 있다.
전달 후 파일 손상 여부를 확인할 때 이 값을 비교한다.

## 12. 필요한 Python 패키지

모델 로딩/추론에는 최소한 아래 계열 패키지가 필요하다.

- `joblib`
- `scikit-learn`
- `lightgbm`
- `pandas`
- `numpy`

프로젝트 전체 실행 환경은 repository의 `pyproject.toml`과 `uv.lock`을 기준으로 맞춘다.
