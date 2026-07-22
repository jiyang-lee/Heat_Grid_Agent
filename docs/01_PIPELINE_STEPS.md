# Pipeline Steps

## 실행 모드

| 모드 | 명령 | 용도 |
|---|---|---|
| 저장소 재현 | `uv run third-model-pipeline --steps all` | GitHub/전달용 기본 실행. 보존 산출물로 최종 card 재생성 |
| 보호된 전체 재생성 | `uv run third-model-pipeline --steps full_retrain` | 검증된 Risk·Leadtime artifact를 유지한 채 점수·Priority·M1 specialist·검증 산출물 갱신 |

## full_retrain 순서

```text
raw
windows
model_artifacts
anomaly
retrain_current_best
merge
agent_card
retrain_m1_specialist
m1_specialist_gates
m1_specialist
validation
```

## Step 설명

| step | 입력 | 출력 | 설명 |
|---|---|---|---|
| `retrain_current_best` | package-local M1 windows + 검증 artifact | risk/leadtime/priority score, retrain metadata | 기본은 검증된 Risk·Leadtime joblib을 재사용해 점수만 재생성. 모델 교체 실험은 명시적 env 필요 |
| `raw` | source raw folder | `data/interim/raw_inventory.csv`, `raw_schema_summary.csv` | raw 파일 존재와 schema 확인 |
| `windows` | source `trainable_windows.csv` | `data/processed/trainable_windows.csv` | canonical window를 M1만 필터링 |
| `model_artifacts` | source 또는 저장소 보존 model metadata | `models/model_artifacts_metadata.json` | risk/leadtime joblib, priority metadata materialize |
| `anomaly` | M1 trainable windows | `models/anomaly/`, `output/anomaly_scores.csv` | M1 anomaly 모델과 score 재생성 |
| `best_scores` | source 또는 저장소 보존 risk/leadtime/priority score | `output/risk_scores.csv`, `output/leadtime_scores.csv`, `output/priority_scores.csv` | current-best score를 M1 범위로 bridge |
| `merge` | priority + anomaly | `output/merged_model_scores.csv` | key 기준 병합 |
| `agent_card` | merged score | `output/agent_priority_card.csv`, schema/dictionary | 최종 agent 입력 계약 생성 |
| `retrain_m1_specialist` | `artifacts/m1_specialist/training_inputs/` | `models/m1_specialist/`, retrain metadata | fault/task/activity/pre-event gate joblib package-local retrain |
| `m1_specialist_gates` | M1 gate joblib + raw compact features | `output/m1_specialist_gate_scores.csv`, parallel card | M1 단독 병렬 evidence score |
| `m1_specialist` | current-best priority + M1 specialist score | `output/m1_specialist_scores.csv`, `output/agent/m1_agent_priority_card.csv` | hybrid priority 결합 |
| `validation` | 모든 score/card | `output/reports/` | coverage, threshold, ablation, report 산출 |

## raw to trainable_windows

이 저장소는 current-best source가 만든 canonical `trainable_windows.csv`를 M1 범위로 연결한다. raw CSV에서 canonical window를 다시 만드는 책임은 current-best source pipeline에 있다. 기본 `full_retrain`은 검증된 Risk·Leadtime artifact를 덮어쓰지 않고 점수와 downstream card를 재생성한다. 모델 교체 실험에만 `THIRD_MODEL_RISK_MODEL_MODE=retrain`, `THIRD_MODEL_LEADTIME_MODEL_MODE=retrain`을 명시한다.

## coverage 해석

M1 canonical window는 1252개다. 내부 `full_retrain` 기준 final hybrid agent card도 1252개 key를 보존한다. 예전 보존 score bridge 경로에서 보이던 partial coverage는 legacy 비교 맥락으로만 해석한다.

확인 파일:

```text
output/reports/key_coverage_by_artifact.csv
output/reports/missing_agent_windows.csv
output/reports/row_flow_summary.csv
```
# 2026-07-08 Internal Full Retrain Update

`full_retrain` is now package-local by default:

```text
raw -> windows -> model_artifacts -> anomaly -> retrain_current_best
-> merge -> agent_card -> retrain_m1_specialist
-> m1_specialist_gates -> m1_specialist -> validation
```

`retrain_current_best` generates M1 risk, leadtime, and priority outputs inside this repository while reusing the validated packaged Risk/Leadtime artifacts by default. Set `THIRD_MODEL_RISK_MODEL_MODE=retrain` or `THIRD_MODEL_LEADTIME_MODEL_MODE=retrain` only for an explicit replacement experiment. The old external current-best wrapper remains available with `THIRD_MODEL_CURRENT_BEST_RETRAIN_MODE=external`.

`retrain_m1_specialist` no longer requires `THIRD_MODEL_3RD_PROJECT_ROOT` after the package-local training inputs exist. It trains the fault/task/activity/pre-event gate joblibs from `artifacts/m1_specialist/training_inputs/`. If those inputs are missing, the first internal run can bootstrap them from `THIRD_MODEL_3RD_PROJECT_ROOT`; use `THIRD_MODEL_M1_SPECIALIST_RETRAIN_MODE=external` for the original source-project retrain.
