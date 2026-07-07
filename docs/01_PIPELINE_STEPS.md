# Pipeline Steps

## 실행 모드

| 모드 | 명령 | 용도 |
|---|---|---|
| 저장소 재현 | `uv run python run_3rd_model_pipeline.py --steps all` | GitHub/전달용 기본 실행. 보존 산출물로 최종 card 재생성 |
| 원천 재학습 포함 | `uv run python run_3rd_model_pipeline.py --steps full_retrain` | current-best와 M1 specialist source를 다시 학습한 뒤 저장소 결과 갱신 |

## full_retrain 순서

```text
retrain_current_best
raw
windows
model_artifacts
anomaly
best_scores
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
| `retrain_current_best` | `../HeatGrid_Agent/best` | `models/risk`, `models/leadtime`, `models/priority`, retrain metadata | source current-best에서 anomaly/multi-window/risk/leadtime/priority/report/ops_eval 재실행 |
| `raw` | source raw folder | `data/interim/raw_inventory.csv`, `raw_schema_summary.csv` | raw 파일 존재와 schema 확인 |
| `windows` | source `trainable_windows.csv` | `data/processed/trainable_windows.csv` | canonical window를 M1만 필터링 |
| `model_artifacts` | source 또는 packaged model metadata | `models/model_artifacts_metadata.json` | risk/leadtime joblib, priority metadata materialize |
| `anomaly` | M1 trainable windows | `models/anomaly/`, `output/anomaly_scores.csv` | M1 anomaly 모델과 score 재생성 |
| `best_scores` | source 또는 packaged risk/leadtime/priority score | `output/risk_scores.csv`, `output/leadtime_scores.csv`, `output/priority_scores.csv` | current-best score를 M1 범위로 bridge |
| `merge` | priority + anomaly | `output/merged_model_scores.csv` | key 기준 병합 |
| `agent_card` | merged score | `output/agent_priority_card.csv`, schema/dictionary | 최종 agent 입력 계약 생성 |
| `retrain_m1_specialist` | M1 specialist source + PreDist zip | `models/m1_specialist/`, retrain metadata | fault/task/activity/pre-event gate joblib 재학습 |
| `m1_specialist_gates` | M1 gate joblib + raw compact features | `output/m1_specialist_gate_scores.csv`, parallel card | M1 단독 병렬 evidence score |
| `m1_specialist` | current-best priority + M1 specialist score | `output/m1_specialist_scores.csv`, `output/agent/m1_agent_priority_card.csv` | hybrid priority 결합 |
| `validation` | 모든 score/card | `output/reports/` | coverage, threshold, ablation, report 산출 |

## raw to trainable_windows

이 저장소는 current-best source가 만든 canonical `trainable_windows.csv`를 M1 범위로 연결한다. raw CSV에서 canonical window를 다시 만드는 책임은 current-best source pipeline에 있다. 즉 `full_retrain`은 source pipeline을 먼저 실행하고, 그 결과를 현재 저장소 산출물로 갱신한 뒤 downstream agent card를 만든다.

## coverage 해석

M1 canonical window는 1252개다. final hybrid agent card는 current-best priority/card key를 기준으로 하므로 1226개가 남는다. 빠진 26개는 모두 `pre_fault` window이며, 단순 row 유실이 아니라 source priority/card 산출 범위 차이다.

확인 파일:

```text
output/reports/key_coverage_by_artifact.csv
output/reports/missing_agent_windows.csv
output/reports/row_flow_summary.csv
```
