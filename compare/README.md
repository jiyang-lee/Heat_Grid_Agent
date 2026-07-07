# M1 Specialist 보고용 성능비교 노트북

## 파일

- `m1_specialist_performance_comparison.ipynb`: 발표/보고용으로 정리한 실행 완료 Plotly 비교 노트북
- `generate_m1_performance_comparison_notebook.py`: 위 노트북을 재생성하는 스크립트
- `m1_threshold_weight_rationale_report.ipynb`: threshold, risk/leadtime/anomaly weight, priority engine, hybrid 0.65/0.35 근거를 정리한 실행 완료 Plotly 보고서
- `generate_threshold_weight_rationale_notebook.py`: threshold/weight 근거 보고서를 재생성하는 스크립트
- `../output/reports/anomaly_if_mahalanobis_policy_grid.csv`: IF/Mahalanobis ratio threshold 조합별 anomaly 성능 grid
- `../output/reports/row_flow_summary.csv`: source canonical, M1 canonical, current-best score bridge, final agent row 흐름 요약
- `../output/reports/key_coverage_by_artifact.csv`: risk/leadtime/priority/card별 key coverage와 missing 26개 row 추적
- `../output/reports/risk_level_actual_summary.csv`: 실제 M1 risk level 분포와 score 범위
- `../output/reports/risk_threshold_actual_values.csv`: `risk_scores.csv`에 실제 적용된 risk threshold 값
- `../output/reports/m1_gate_threshold_sweep.csv`: fault/task/activity/pre-event gate threshold sweep
- `../output/reports/m1_gate_selected_threshold_summary.csv`: 현재 runtime policy threshold 0.50/0.60에서의 지표
- `../output/reports/m1_gate_threshold_reference.csv`: 현재 threshold와 대안 후보/FPR guardrail 후보 비교
- `../output/reports/m1_specialist_priority_weight_ablation.csv`: M1 specialist 0.55/0.30/0.15 및 ablation 비교
- `../output/reports/m1_specialist_priority_weight_grid.csv`: M1 specialist 내부 weight grid
- `../output/reports/fault_group_weight_summary.csv`: fault group별 weight, 빈도, pre_fault 분포 요약
- `../output/reports/level_calibration_fpr_cap_sweep.csv`: FPR cap 0.05/0.10/0.15/0.20 level calibration 비교
- `../output/reports/hybrid_selected_weight_comparison.csv`: 0.65/0.35, 0.72/0.28, 0.90/0.10 핵심 비교
- `../output/reports/hybrid_065_vs_072_metric_delta.csv`: 0.65/0.35와 0.72/0.28의 split별 성능 차이
- `../output/reports/hybrid_065_vs_072_level_transition.csv`: 0.65에서 0.72 변경 시 priority level 이동 집계
- `../output/reports/hybrid_065_vs_072_changed_rows.csv`: level이 실제로 바뀐 row 목록

## 범위

이 노트북은 저장소 내부 최종본과 `artifacts/current_best/`에 보존된 이전 실험 CSV 중 최종 의사결정에 실제로 영향을 준 비교만 사용한다.

보고용 핵심 비교 축:

- anomaly 대표 정책 비교와 evidence 역할 설명
- IF 0.90 / Mahalanobis 1.00 / criticality 5 설정 근거와 threshold grid
- `2526 -> 1252 -> 1226` row flow 및 missing 26개 row의 성격
- current-best risk/leadtime 개선 근거
- risk 후보군 중 official/base/calibrated/promoted/current-best 비교
- leadtime bucket 설계 및 current-best 개선 비교
- rule-based priority와 LGBM priority 핵심 후보 비교
- 최종 M1 hybrid priority 도출 근거
- anomaly/risk/priority/hybrid threshold 설정 근거
- 실제 M1 risk applied threshold가 0.22/0.92/0.92이고, 0.44는 active M1 output 기준이 아니라는 점
- risk가 priority engine에서 가장 큰 축으로 들어가는 이유
- leadtime과 anomaly가 보조 신호로 남은 이유
- hybrid engine이 0.65 / 0.35로 잡힌 이유와 0.00~1.00 전구간 weight sweep
- 0.65가 절대 metric-best가 아니라 운영 선택점이며, 0.72/0.28과 0.90/0.10을 함께 비교
- 0.65/0.35에서 0.72/0.28로 바꿀 때 FP, precision, FPR, level 이동, score delta가 어떻게 달라지는지 별도 Plotly 섹션으로 비교
- M1 specialist gate threshold가 독립 알람 최적값이 아니라 evidence runtime policy라는 점, 내부 priority weight ablation, fault_group_weight의 live inference 제한사항
- level calibration FPR cap 0.05/0.10/0.15/0.20 비교와 현재 cap이 threshold를 바꾸지 않았다는 해석
- active policy ablation 기반 최종 contract 해석
- label/proxy, row reconciliation, 표본 수 관련 고려사항

## 실행

```powershell
cd Heat_Grid_Agent
uv sync
uv run python compare\generate_m1_performance_comparison_notebook.py
uv run python compare\generate_threshold_weight_rationale_notebook.py
```

노트북을 다시 실행하려면 `plotly`, `nbformat`, `nbclient`, `ipykernel`이 필요하다.

저장소 위치를 옮긴 경우에는 실행 전에 `M1_SPECIALIST_REPO_ROOT` 환경변수를 새 저장소 경로로 지정한다.
