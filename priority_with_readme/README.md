# HeatGrid Priority Regression Code Package

이 ZIP은 HeatGrid Agent의 우선순위 회귀모델 관련 Python 코드 파일 묶음이다.

## 목적

중간 예측 모델 체인 output(`model_chain_output.csv`)을 입력으로 받아 운영 점검 우선순위 점수(`priority_score`)와 등급(`priority_level`)을 만들기 위한 학습/평가/추론 코드를 담고 있다.

전체 흐름은 다음과 같다.

```text
model_chain_output.csv
-> build_dataset.py
-> train_priority_model.py
-> lightgbm_priority_model.joblib
-> run_priority.py
-> priority_scores.csv
```

## 주요 파일

| 파일 | 역할 |
|---|---|
| `contracts.py` | priority 입력 7개 feature, score band, model version 정의 |
| `build_dataset.py` | `model_chain_output.csv`에서 학습 target과 feature matrix 구성 |
| `train_priority_model.py` | LightGBM 회귀모델 학습 및 joblib/metadata 저장 |
| `evaluate.py` | holdout ranking metric과 rule baseline 비교 |
| `rule_baseline.py` | 기존 rule 기반 priority baseline 재구성 |
| `run_priority.py` | 학습된 회귀모델로 `priority_scores.csv` 생성 |
| `validate_contracts.py` | priority 입출력 계약 검증 |
| `generate_mock.py` | 과거 mock ML output 생성 보조 코드. 현재 정본 학습 기준은 아님 |

## 현재 정본 모델 기준

현재 proto 완성본의 priority 모델은 mock ML output이 아니라 실제 모델 체인 output을 기준으로 학습한다.

- 입력: `data/processed/ml_model_chain/model_chain_output.csv`
- 모델 타입: `LGBMRegressor`
- 모델 버전: `priority_v3_lgbm_reg`
- 입력 feature 수: 7개
- target label: `normal=0`, `3-7d=33`, `1-3d=66`, `0-24h=100`

## Priority 입력 feature 7개

```text
anomaly_score
risk_probability
risk_score
leadtime_prob_0-24h
leadtime_prob_1-3d
leadtime_prob_3-7d
predicted_lead_time_confidence
```

## 실행 예시

repo 루트에서 실행한다.

```powershell
uv run python -m agent.priority.train_priority_model
uv run python -m agent.priority.run_priority
uv run python -m agent.priority.evaluate
```

## 산출물 위치

```text
agent/priority/models/lightgbm_priority_model.joblib
agent/priority/models/priority_model_metadata.json
data/processed/ml_priority/priority_scores.csv
```

## 주의사항

- 이 ZIP은 코드 묶음이며, 학습된 `.joblib` 모델 파일은 포함하지 않는다.
- 학습/추론을 재현하려면 repo의 `agent/priority/models/`와 `data/processed/ml_model_chain/model_chain_output.csv`가 필요하다.
- `generate_mock.py`는 과거 mock 데이터 생성용 보조 파일이며, proto 완성본의 정본 학습 경로는 `model_chain_output.csv` 기준이다.
