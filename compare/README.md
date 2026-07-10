# 비교 실험 및 보고용 노트북

`compare/`는 발표/보고용 성능 비교와 threshold/weight 선택 근거를 담는 폴더다. Plotly 차트가 포함된 실행 완료 notebook과 이를 재생성하는 script를 함께 둔다.

## 핵심 파일

| 파일 | 설명 |
|---|---|
| `m1_specialist_performance_comparison.ipynb` | 최종본 도출 과정, 모델 후보 비교, 신뢰도와 고려사항 |
| `m1_threshold_weight_rationale_report.ipynb` | anomaly/risk/leadtime/priority threshold와 weight 선택 근거 |
| `generate_m1_performance_comparison_notebook.py` | 성능 비교 notebook 재생성 |
| `generate_threshold_weight_rationale_notebook.py` | threshold/weight 근거 notebook 재생성 |

## 재생성

```powershell
uv run python compare\generate_m1_performance_comparison_notebook.py
uv run python compare\generate_threshold_weight_rationale_notebook.py
```

노트북 실행 확인:

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

## 보고서에서 다루는 핵심 질문

| 질문 | 근거 파일 |
|---|---|
| 왜 M1-only scope인가 | `output/reports/m1_scope_audit.md`, `docs/08_MODEL_REPORT_DEFENSE_AUDIT.md` |
| 1252 -> 1226 row 차이는 무엇인가 | `output/reports/row_flow_summary.csv`, `key_coverage_by_artifact.csv`, `missing_agent_windows.csv` |
| IF 0.90 / Mahalanobis 1.00을 왜 쓰는가 | `output/reports/anomaly_if_mahalanobis_policy_grid.csv` |
| criticality 5를 왜 쓰는가 | `output/reports/anomaly_criticality_threshold_sweep.csv` |
| risk level 기준은 실제로 얼마인가 | `output/reports/risk_threshold_actual_values.csv`, `risk_level_actual_summary.csv` |
| M1 gate 0.50 / 0.60은 어떤 의미인가 | `output/reports/m1_gate_threshold_sweep.csv`, `m1_gate_threshold_reference.csv` |
| M1 specialist 내부 weight 0.55/0.30/0.15 근거는 무엇인가 | `output/reports/m1_specialist_priority_weight_ablation.csv`, `m1_specialist_priority_weight_grid.csv` |
| hybrid 0.65/0.35가 best인가 | `output/reports/hybrid_weight_sweep.csv`, `hybrid_selected_weight_comparison.csv` |
| FPR cap 0.20은 어떤 의미인가 | `output/reports/level_calibration_fpr_cap_sweep.csv` |

## 주요 보고 포인트

- `0.65 / 0.35`는 절대 metric-best가 아니라 운영 선택점이다.
- `0.72 / 0.28`, `0.90 / 0.10`과 비교해서 precision/FPR/level 이동을 함께 설명한다.
- M1 specialist gate threshold는 standalone alarm optimum이 아니라 evidence runtime policy다.
- task/activity gate는 native label 부재 때문에 true performance claim을 제한한다.
- `fault_group_weight`는 label-derived 성격이 있어 live inference에서는 별도 검토가 필요하다.
- level calibration의 `FPR <= 0.20`은 현재 sweep에서 threshold 차이를 크게 만들지 않았고, future validation 분포에 대한 운영 guardrail로 설명한다.

## Scope

이 폴더의 notebook은 저장소 내부 최종본과 `artifacts/current_best/`에 보존된 이전 실험 CSV 중 최종 의사결정에 영향을 준 비교만 사용한다. 비교조차 어려운 폐기 실험은 보고 흐름에 포함하지 않는다.
