# M1 Specialist Handoff

## 결론

- 이 저장소는 `manufacturer 1` 기준 최종 모델/agent 산출물 전달본이다.
- 최종 agent card는 `output/agent_priority_card.csv`와 `output/agent/m1_agent_priority_card.csv`다.
- 최종 card는 `1226 rows / 55 columns`다.
- `output/agent/m1_specialist_parallel_agent_card.csv`는 `1252 rows / 29 columns`의 M1 단독 병렬 evidence card이며, 최종 ordering contract가 아니다.
- 최종 `priority_score`는 `0.65 * current_best_priority_score + 0.35 * m1_specialist_priority_score` hybrid다.

## 실행

저장소 재현:

```powershell
uv sync
uv run python run_3rd_model_pipeline.py --steps all
```

원천 재학습 포함 전체 재생성:

```powershell
uv run python run_3rd_model_pipeline.py --steps full_retrain
```

`full_retrain`은 current-best source와 M1 specialist source가 함께 있을 때 사용한다. 실행 로그는 `output/reports/retrain_logs/`에 남는다.

## 먼저 볼 파일

```text
README.md
PACKAGE_README_KO.md
MODEL_INVENTORY_KO.md
PACKAGE_MANIFEST.md
docs/00_SOURCE_TRACE.md
docs/01_PIPELINE_STEPS.md
docs/05_RUNBOOK.md
docs/07_HANDOFF_FILE_INDEX.md
output/agent/agent_card_column_groups_ko.md
output/reports/final_validation_report.md
compare/m1_threshold_weight_rationale_report.ipynb
```

## 모델 계열

| 계열 | 역할 | 최종 card 반영 |
|---|---|---|
| Current-best risk | supervised pre_fault 위험 신호 | 포함 |
| Current-best leadtime | 시간 긴급도 참고 신호 | 포함 |
| Current-best priority | baseline priority body | 포함 |
| M1 anomaly | IF/Mahalanobis 기반 정상 이탈 evidence | 포함 |
| M1 specialist gates | M1 fault/task/activity/pre-event 병렬 evidence | 포함, 35% hybrid input |
| Agent operation layer | review, trust, why, action | 포함 |

## 제한 사항

- 현재 검증 범위는 M1이다. M2나 전체 제조사 성능으로 일반화하지 않는다.
- `risk_model_best.joblib`, `leadtime_model_best.joblib`, `priority_engine_best_metadata.json`은 저장소에 포함되며, `full_retrain` 실행 시 source 결과로 갱신된다.
- 실제 M1 risk level 기준은 `medium=0.22`, `high=0.92`, `critical=0.92`다.
- M1 gate threshold `0.50/0.60`은 단독 알람 최적값이 아니라 specialist evidence runtime policy다.
- missing 26 rows는 M1 canonical 1252개 중 current-best priority/card 산출 범위에 없던 `pre_fault` window다. 이 내용은 coverage 보고서에 포함되어야 한다.
