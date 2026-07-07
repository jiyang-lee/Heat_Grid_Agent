# 실행 Runbook

실행, 재학습, 검증, 공개 전 확인 명령을 모아 둔 문서다.

## 1. 환경 준비

```powershell
uv sync
uv run python --version
```

Python은 3.12 계열이어야 한다.

## 2. 저장소 단독 재현

```powershell
uv run python run_3rd_model_pipeline.py --steps all
```

source 프로젝트가 없어도 저장소 내부 보존 파일로 최종 산출물을 재생성한다.

주요 결과:

```text
output/agent_priority_card.csv
output/agent/m1_agent_priority_card.csv
output/agent/m1_specialist_parallel_agent_card.csv
output/reports/final_validation_report.md
```

## 3. 원천 재학습 포함 전체 실행

```powershell
uv run python run_3rd_model_pipeline.py --steps full_retrain
```

필요 source:

```text
../HeatGrid_Agent/best
../3rd_project_for_ML-main/3rd_project_for_ML-main
```

다른 위치면 환경변수로 지정한다.

```powershell
$env:THIRD_MODEL_SOURCE_BEST_ROOT="D:\path\HeatGrid_Agent\best"
$env:THIRD_MODEL_3RD_PROJECT_ROOT="D:\path\3rd_project_for_ML-main"
$env:THIRD_MODEL_PREDIST_ZIP_PATH="D:\path\predist_dataset.zip"
```

재학습 로그:

```text
output/reports/retrain_logs/retrain_current_best.log
output/reports/retrain_logs/retrain_m1_specialist.log
output/reports/source_retrain_metadata.json
output/reports/m1_source_retrain_metadata.json
```

## 4. 개별 재학습

current-best risk/leadtime/priority 계열:

```powershell
uv run python run_3rd_model_pipeline.py --steps retrain_current_best
```

M1 specialist gate 모델:

```powershell
uv run python run_3rd_model_pipeline.py --steps retrain_m1_specialist
```

## 5. 부분 실행

Anomaly와 downstream card만 다시 생성:

```powershell
uv run python run_3rd_model_pipeline.py --steps model_artifacts anomaly best_scores merge agent_card m1_specialist_gates m1_specialist validation
```

Validation만 다시 생성:

```powershell
uv run python run_3rd_model_pipeline.py --steps validation
```

## 6. Notebook 재생성

```powershell
uv run python compare\generate_m1_performance_comparison_notebook.py
uv run python compare\generate_threshold_weight_rationale_notebook.py
```

Notebook 실행 확인:

```powershell
@'
from pathlib import Path
import nbformat
from nbclient import NotebookClient

for path in [
    Path("compare/m1_specialist_performance_comparison.ipynb"),
    Path("compare/m1_threshold_weight_rationale_report.ipynb"),
]:
    nb = nbformat.read(path, as_version=4)
    NotebookClient(nb, timeout=1200, kernel_name="python3").execute()
    print("OK", path)
'@ | uv run python -
```

## 7. 테스트

```powershell
uv run python -m unittest discover -s tests -v
```

## 8. 공개 전 확인

```powershell
uv run python -m unittest discover -s tests -v
uv run python run_3rd_model_pipeline.py --steps all
git status --short
```

절대경로나 과거 전달본 표현이 남았는지 확인:

```powershell
rg -n "Project3|m1_specialist[_-][p]ackage|1550.*1226" README.md docs compare scripts src output\reports output\agent -g "!*.csv"
```

`full_retrain`은 source 프로젝트가 있는 환경에서만 공개 전 추가 검증한다.
