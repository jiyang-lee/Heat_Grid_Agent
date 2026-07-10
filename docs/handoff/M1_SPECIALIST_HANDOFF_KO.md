# M1 Specialist Handoff

M1 specialist 계열이 최종 agent card에서 어떤 역할을 하는지 정리한 인계 문서다.

## 결론

| 항목 | 내용 |
|---|---|
| 검증 범위 | `manufacturer 1` |
| 최종 agent card | `output/agent_priority_card.csv`, `output/agent/m1_agent_priority_card.csv` |
| 최종 card 크기 | 1226 rows / 55 columns |
| M1 specialist 병렬 card | `output/agent/m1_specialist_parallel_agent_card.csv` |
| 병렬 card 크기 | 1252 rows / 29 columns |
| 최종 priority | `0.65 * current_best_priority_score + 0.35 * m1_specialist_priority_score` |

M1 specialist는 current-best risk/leadtime/priority를 대체하지 않는다. M1 gate 기반 evidence를 별도 branch로 계산하고, 최종 priority에 35% 반영한다.

## 실행

저장소 단독 재현:

```powershell
uv sync
uv run third-model-pipeline --steps all
```

원천 재학습 포함:

```powershell
uv run third-model-pipeline --steps full_retrain
```

`full_retrain` 실행 로그:

```text
output/reports/retrain_logs/retrain_current_best.log
output/reports/retrain_logs/retrain_m1_specialist.log
output/reports/source_retrain_metadata.json
output/reports/m1_source_retrain_metadata.json
```

## M1 specialist 구성

| 구성 | 파일 | threshold | 역할 |
|---|---|---:|---|
| fault gate | `models/m1_specialist/m1_fault_gate_rf_depth3.joblib` | 0.50 | fault evidence |
| task gate | `models/m1_specialist/m1_task_gate_rf_depth3.joblib` | 0.50 | task evidence |
| activity gate | `models/m1_specialist/m1_activity_gate_rf_depth3.joblib` | 0.50 | activity evidence |
| pre-event gate | `models/m1_specialist/m1_fault_pre_event_logistic.joblib` | 0.60 | event 선행 evidence |

Gate threshold는 단독 알람 최적값이 아니라 specialist evidence runtime policy로 설명한다. task/activity는 native target label이 부족하므로 성능 claim보다 evidence 산출 관점으로 해석한다.

## 최종 priority 결합

M1 specialist 내부 priority:

```text
m1_specialist_priority_score
= 100 * (
    0.55 * pre_event_probability
  + 0.30 * leadtime_urgency
  + 0.15 * fault_group_weight
)
```

최종 hybrid priority:

```text
m1_hybrid_priority_score
= 0.65 * current_best_priority_score
 + 0.35 * m1_specialist_priority_score
```

`0.65 / 0.35`는 운영 선택점이다. 비교 후보 `0.72 / 0.28`, `0.90 / 0.10`은 `output/reports/hybrid_selected_weight_comparison.csv`와 `compare/m1_threshold_weight_rationale_report.ipynb`에 남긴다.

## 먼저 볼 파일

| 파일 | 역할 |
|---|---|
| `docs/README.md` | 전체 문서 지도 |
| `docs/model/MODEL_INVENTORY_KO.md` | 모델 구성과 재학습 책임 |
| `docs/02_AGENT_OUTPUT_CONTRACT.md` | agent card 컬럼 계약 |
| `output/agent/agent_card_column_groups_ko.md` | 최종 55개 컬럼과 병렬 29개 컬럼 분류 |
| `output/reports/final_validation_report.md` | 최종 검증 요약 |
| `compare/m1_threshold_weight_rationale_report.ipynb` | threshold/weight 선택 근거 |

## 제한 사항

- 현재 검증 범위는 M1이다. M2나 전체 제조사 성능으로 일반화하지 않는다.
- `fault_group_weight`는 현재 fault label 파생 성격이 강하므로 live inference에서는 별도 label-free 정책 검토가 필요하다.
- final card는 1226 rows이고, M1 specialist parallel card는 1252 rows다. 두 파일을 혼동하지 않는다.
- missing 26 rows는 current-best priority/card 산출 범위에 없던 `pre_fault` window다.
