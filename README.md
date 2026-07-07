# M1 Specialist HeatGrid 저장소

이 저장소는 `manufacturer 1` 기준 HeatGrid 모델 산출물을 재현하고, agent card까지 생성하는 실행 저장소다. 기본 실행은 저장소 내부 보존 산출물로 재현되며, `full_retrain` 실행은 원천 current-best 프로젝트와 M1 specialist 프로젝트를 다시 학습한 뒤 결과를 현재 저장소 산출물로 갱신한다.

## 실행 환경

```powershell
uv sync
uv run python --version
```

- Python은 `.python-version` 기준 `3.12`다.
- 저장소 기본 실행은 `uv` 환경만으로 동작한다.
- current-best 원천 재학습은 원천 코드가 `torch`를 import하므로, 발견된 source venv(`../HeatGrid_Agent/.venv`)를 우선 사용한다. 강제로 현재 uv Python을 쓰려면 `THIRD_MODEL_CURRENT_BEST_PYTHON`을 지정하고 해당 환경에 source 의존성을 설치한다.

## 두 가지 실행 모드

### 1. 저장소 단독 재현

GitHub에 올린 뒤 받는 사람이 가장 먼저 실행할 모드다. source 프로젝트가 없으면 저장소에 보존된 `artifacts/current_best/`, `models/`, `data/processed/`를 사용한다.

```powershell
uv run python run_3rd_model_pipeline.py --steps all
```

실행 순서:

```text
raw -> windows -> model_artifacts -> anomaly -> best_scores -> merge
-> agent_card -> m1_specialist_gates -> m1_specialist -> validation
```

### 2. 원천 재학습 포함 전체 재생성

원래 프로젝트 폴더가 함께 있을 때 risk/leadtime/priority/M1 gate까지 다시 만들고 최종 산출물을 갱신하는 모드다.

```powershell
uv run python run_3rd_model_pipeline.py --steps full_retrain
```

실행 순서:

```text
retrain_current_best
-> raw -> windows -> model_artifacts -> anomaly -> best_scores -> merge -> agent_card
-> retrain_m1_specialist
-> m1_specialist_gates -> m1_specialist -> validation
```

개별 재학습도 가능하다.

```powershell
uv run python run_3rd_model_pipeline.py --steps retrain_current_best
uv run python run_3rd_model_pipeline.py --steps retrain_m1_specialist
```

## 원천 프로젝트 탐색

절대경로를 코드에 고정하지 않는다. 아래 환경변수가 있으면 우선 사용하고, 없으면 sibling 폴더를 자동 탐색한다.

| 변수 | 역할 |
|---|---|
| `THIRD_MODEL_SOURCE_BEST_ROOT` | current-best source root. 기본 탐색 후보: `../HeatGrid_Agent/best` |
| `THIRD_MODEL_CURRENT_BEST_PYTHON` | current-best source 재학습용 Python |
| `THIRD_MODEL_3RD_PROJECT_ROOT` | M1 specialist source root. 기본 탐색 후보: `../3rd_project_for_ML-main/3rd_project_for_ML-main` |
| `THIRD_MODEL_M1_SPECIALIST_PYTHON` | M1 specialist source 재학습용 Python. 기본값은 현재 uv Python |
| `THIRD_MODEL_PREDIST_ZIP_PATH` | M1 specialist source에 `predist_dataset.zip`이 없을 때 사용할 원본 zip |

M1 source 재학습은 source 폴더 안 `05_데이터셋/PreDist/predist_dataset.zip`을 요구한다. 없으면 파이프라인이 `THIRD_MODEL_PREDIST_ZIP_PATH` 또는 `../HeatGrid_Agent/data/_downloads/predist_dataset.zip`를 찾아 복사한다.

## 주요 산출물

```text
output/agent_priority_card.csv
output/agent/m1_agent_priority_card.csv
output/agent/m1_specialist_parallel_agent_card.csv
output/agent/agent_card_column_groups_ko.md
output/reports/final_validation_report.md
output/reports/source_retrain_metadata.json
output/reports/m1_source_retrain_metadata.json
output/reports/retrain_logs/
models/risk/risk_model_best.joblib
models/leadtime/leadtime_model_best.joblib
models/priority/priority_engine_best_metadata.json
models/m1_specialist/
compare/m1_specialist_performance_comparison.ipynb
compare/m1_threshold_weight_rationale_report.ipynb
```

현재 최종 card는 `1226 rows / 55 columns`이고, M1 specialist 병렬 evidence card는 `1252 rows / 29 columns`다. 빠진 26개는 current-best priority/card 산출 단계에서 제외된 `pre_fault` window이며, coverage 해석은 `output/reports/key_coverage_by_artifact.csv`와 `output/reports/missing_agent_windows.csv`에 남긴다.

## 검증

```powershell
uv run python -m unittest discover -s tests -v
uv run python run_3rd_model_pipeline.py --steps validation
```

비교 실험과 threshold/weight 근거는 `compare/`의 notebook 두 개를 기준으로 본다. Plotly 차트 title은 발표용으로 한국어 중심으로 정리했다.
