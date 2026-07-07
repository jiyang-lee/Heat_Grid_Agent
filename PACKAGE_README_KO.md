# 저장소 사용 안내

## 목적

`agent/mlmodel` 저장소는 M1 기준 최종 agent card를 재현하고, 필요하면 원천 모델까지 다시 학습해 저장소 산출물을 갱신하는 실행 단위다.

## 바로 실행

```powershell
uv sync
uv run python run_3rd_model_pipeline.py --steps all
uv run python -m unittest discover -s tests -v
```

`all`은 저장소 내부 보존 산출물을 사용해 최종 결과를 재생성한다. 외부 source 프로젝트가 없어도 동작해야 하는 기본 경로다.

## 원천 재학습 포함 실행

```powershell
uv run python run_3rd_model_pipeline.py --steps full_retrain
```

`full_retrain`은 다음 순서로 돈다.

```text
1. current-best source에서 anomaly/risk/leadtime/priority 재학습
2. risk_model_best.joblib, leadtime_model_best.joblib, priority metadata를 현재 저장소 산출물로 갱신
3. M1 canonical windows와 best score를 현재 저장소 기준으로 연결
4. M1 anomaly, merge, agent card 생성
5. M1 specialist source에서 fault/task/activity/pre-event gate joblib 재학습
6. M1 specialist 모델을 현재 저장소 산출물로 갱신
7. 최종 hybrid priority와 validation 산출
```

## source 경로

코드는 절대경로를 고정하지 않는다. 같은 상위 폴더에 아래 프로젝트가 있으면 자동 탐색한다.

```text
../HeatGrid_Agent/best
../3rd_project_for_ML-main/3rd_project_for_ML-main
```

다른 위치에 있으면 환경변수로 지정한다.

```powershell
$env:THIRD_MODEL_SOURCE_BEST_ROOT="D:\...\HeatGrid_Agent\best"
$env:THIRD_MODEL_3RD_PROJECT_ROOT="D:\...\3rd_project_for_ML-main"
$env:THIRD_MODEL_PREDIST_ZIP_PATH="D:\...\predist_dataset.zip"
```

## 받는 사람이 먼저 볼 파일

```text
README.md
M1_SPECIALIST_HANDOFF_KO.md
MODEL_INVENTORY_KO.md
PACKAGE_MANIFEST.md
docs/05_RUNBOOK.md
docs/07_HANDOFF_FILE_INDEX.md
output/reports/final_validation_report.md
compare/m1_threshold_weight_rationale_report.ipynb
```

## 최종 card

| 파일 | 역할 | rows | columns |
|---|---|---:|---:|
| `output/agent_priority_card.csv` | 최종 hybrid agent card | 1226 | 55 |
| `output/agent/m1_agent_priority_card.csv` | 최종 hybrid card 복사본 | 1226 | 55 |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 단독 병렬 evidence card | 1252 | 29 |

최종 card 컬럼 분류는 `output/agent/agent_card_column_groups_ko.md`에 있다.
