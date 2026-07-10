# CODEX 모델 보고서 검토 프롬프트

목표: 모델 보고서가 발표/보고 방어에 충분한지 실제 파일 기준으로 검토하고, 누락된 근거를 보고서와 산출물에 반영한다. 없는 결과를 추정으로 쓰지 않는다.

## 1. 먼저 찾을 파일

프로젝트 전체에서 아래 키워드로 검색한다.

```text
report
model
priority
risk
leadtime
anomaly
threshold
hybrid
metadata
result
performance
README
prompt
```

반드시 확인할 범위:

```text
compare/*.ipynb
compare/*.py
docs/*.md
docs/model/MODEL_INVENTORY_KO.md
docs/handoff/AGENT_HANDOFF_KO.md
docs/package/PACKAGE_MANIFEST.md
output/reports/*.csv
output/reports/*.md
output/reports/*.json
models/**/*.joblib
models/**/*.json
src/third_model/*.py
artifacts/current_best/**
```

## 2. 필수 점검 항목

각 항목은 아래 형식으로 작성한다.

```text
- 항목명:
  - 포함 여부: 포함 / 부분 포함 / 미포함
  - 현재 위치: 파일명, 섹션명
  - 부족한 점:
  - 추가 필요 내용:
```

점검 항목:

- `risk_model_best.joblib`, `leadtime_model_best.joblib`, `priority_engine_best_metadata.json` 존재와 재현 가능성 설명 여부
- 외부 source 의존성: `THIRD_MODEL_SOURCE_BEST_ROOT`, `THIRD_MODEL_3RD_PROJECT_ROOT`, 같은 상위 폴더 자동 탐색, 저장소 내부 보존본 사용 여부
- raw -> canonical `trainable_windows.csv` 재생성 파이프라인
- M1 canonical 1252 -> final agent 1226, missing 26개 전부 `pre_fault`
- `risk_scores`, `leadtime_scores`, `priority_scores`, `priority_cards` key coverage
- M1-only scope와 M2 calibration 필요성
- IF 0.90 / Mahalanobis 1.00 threshold sweep
- criticality 5 persistence 기준과 1~10 또는 그 이상 sweep
- fault/task/activity gate 0.5, pre-event gate 0.6 threshold sweep
- `risk_scores.csv`의 applied threshold 컬럼 기준 실제 M1 risk level threshold. 과거 fallback/중간 설계값과 active output 값을 분리
- M1 specialist priority weight 0.55/0.30/0.15 ablation
- `fault_group_weight` 빈도, severity, monitoring potential, 동일 weight baseline, live inference 가능성
- hybrid priority 0.65/0.35, 0.72/0.28, 0.90/0.10 비교
- level calibration FPR cap 0.05/0.10/0.15/0.20 비교
- 모델별 성능표와 Plotly 시각화 참조 여부
- 최종 agent card 55 columns와 M1 specialist parallel card 29 columns 구분 여부

## 3. 해석 규칙

- `0.65/0.35`를 절대 최적이라고 쓰지 않는다. validation 안정성, current-best baseline 유지, M1 specialist 반영률을 같이 본 운영 선택점으로 쓴다.
- holdout precision/FPR만 보면 0.72/0.28 또는 0.90/0.10이 같거나 더 좋아 보일 수 있음을 표로 남긴다.
- anomaly는 단독 fault classifier가 아니라 정상 이탈 evidence다.
- `criticality=5`는 anomaly-only recall best가 아니라 지속 evidence threshold다.
- leadtime은 고장 시각 단정값이 아니라 urgency 참고 신호다.
- `fault_group_weight`가 `fault_label` 파생 성격을 가지면 live inference에서 label leakage로 보일 수 있으므로 반드시 제한사항으로 쓴다.
- M1 gate 0.50/0.60은 standalone alarm optimum이 아니라 specialist evidence threshold로 해석한다.
- task/activity gate는 native label이 없으면 성능 claim으로 쓰지 않고 proxy/산출물 한계로 쓴다.
- 현재 M1 risk output의 actual applied threshold가 0.22/0.92/0.92라면, 0.44를 active high threshold처럼 쓰지 않는다.
- M1 결과를 전체 제조사 일반 성능처럼 표현하지 않는다.

## 4. 실험 재실행과 문서 보완 구분

다음 표를 반드시 작성한다.

```markdown
# 실험 재실행 필요 항목

| 항목 | 재실행 필요 여부 | 이유 | 예상 산출물 |
|---|---|---|---|
```

다음 표도 반드시 작성한다.

```markdown
# 문서 보완 항목

| 항목 | 보완 위치 | 추가할 내용 |
|---|---|---|
```

기준:

- 기존 CSV/metadata에서 계산 가능한 것은 문서/노트북 보완으로 처리한다.
- raw 재생성, 새 window 재추론, task/activity native label, M2 calibration, label-free fault group inference는 실험 재실행 필요로 처리한다.

## 5. 산출물 요구

필수 산출물:

```text
docs/08_MODEL_REPORT_DEFENSE_AUDIT.md
compare/m1_threshold_weight_rationale_report.ipynb
output/reports/key_coverage_by_artifact.csv
output/agent/agent_card_column_groups_ko.csv
output/agent/agent_card_column_groups_ko.md
output/reports/risk_level_actual_summary.csv
output/reports/risk_threshold_actual_values.csv
output/reports/m1_gate_threshold_sweep.csv
output/reports/m1_gate_selected_threshold_summary.csv
output/reports/m1_gate_threshold_reference.csv
output/reports/m1_specialist_priority_weight_ablation.csv
output/reports/m1_specialist_priority_weight_grid.csv
output/reports/fault_group_weight_summary.csv
output/reports/level_calibration_fpr_cap_sweep.csv
output/reports/hybrid_selected_weight_comparison.csv
```

보고서에는 Plotly chart title을 한국어 또는 이해 가능한 혼합 표기로 둔다. 제목만 한국어여도 된다.

## 6. 금지

- 실제 파일을 확인하지 않고 추정으로 작성하지 말 것.
- 성능 수치를 임의 생성하지 말 것.
- 없는 모델/CSV를 있다고 쓰지 말 것.
- 0.65/0.35를 best로 단정하지 말 것.
- M1-only 결과를 M2 또는 전체 제조사 성능으로 일반화하지 말 것.
- `fault_group_weight`의 inference risk를 숨기지 말 것.
- M1 gate 0.50/0.60을 최종 알람 최적 threshold처럼 표현하지 말 것.
- 실제 산출물의 applied threshold 컬럼과 다른 오래된 수치를 active threshold처럼 쓰지 말 것.
