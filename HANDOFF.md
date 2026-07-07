# Handoff Summary

이 저장소는 M1 기준 active pipeline 전달본이다.

## 전달 기준

- 최종 agent 입력은 `output/agent_priority_card.csv`다.
- 동일한 최종 card가 `output/agent/m1_agent_priority_card.csv`에도 저장된다.
- 최종 card는 `1226 rows / 55 columns`다.
- `output/agent/m1_specialist_parallel_agent_card.csv`는 `1252 rows / 29 columns`의 M1 단독 병렬 evidence card다.
- 최종 priority는 current-best 65%, M1 specialist 35% hybrid다.

## 다음 담당자가 보는 순서

```text
1. README.md
2. PACKAGE_README_KO.md
3. M1_SPECIALIST_HANDOFF_KO.md
4. MODEL_INVENTORY_KO.md
5. docs/00_SOURCE_TRACE.md
6. docs/01_PIPELINE_STEPS.md
7. docs/05_RUNBOOK.md
8. docs/07_HANDOFF_FILE_INDEX.md
9. output/agent/agent_card_column_groups_ko.md
10. compare/m1_threshold_weight_rationale_report.ipynb
11. output/reports/final_validation_report.md
```

## 재학습

```powershell
uv run python run_3rd_model_pipeline.py --steps all
uv run python run_3rd_model_pipeline.py --steps full_retrain
```

`all`은 저장소 단독 재현, `full_retrain`은 원천 source 재학습 포함 전체 재생성이다.
