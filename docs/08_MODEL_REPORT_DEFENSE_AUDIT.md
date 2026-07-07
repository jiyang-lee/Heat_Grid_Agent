# 모델 보고서 반영 여부 체크리스트

검토 기준일: 2026-07-07

검토 대상:

- `compare/m1_threshold_weight_rationale_report.ipynb`
- `compare/m1_specialist_performance_comparison.ipynb`
- `compare/README.md`
- `MODEL_INVENTORY_KO.md`
- `AGENT_HANDOFF_KO.md`
- `docs/00_SOURCE_TRACE.md` ~ `docs/07_HANDOFF_FILE_INDEX.md`
- `output/reports/*.csv`, `output/reports/*.md`, `output/reports/*.json`
- `src/third_model/*.py`
- `models/**/*.joblib`, `models/**/*.json`

| 항목 | 포함 여부 | 현재 위치 | 부족한 점 | 추가 필요 내용 |
|---|---|---|---|---|
| 누락 모델 파일 및 metadata | 포함 | `MODEL_INVENTORY_KO.md`, `docs/07_HANDOFF_FILE_INDEX.md`, `output/reports/pipeline_run_metadata.json` | 파일 존재는 확인되지만, 기본 실행 경로가 risk/leadtime 재추론이 아니라 current-best score bridge라는 점을 계속 명확히 말해야 함 | `risk_model_best.joblib`, `leadtime_model_best.joblib`, `priority_engine_best_metadata.json`은 포함. 새 window 재계산은 raw/canonical/feature 재생성 파이프라인까지 있어야 완전 재현 가능 |
| 외부 경로 의존성 | 포함 | `src/third_model/config.py`, `docs/00_SOURCE_TRACE.md`, `docs/01_PIPELINE_STEPS.md`, `docs/05_RUNBOOK.md` | 없음 | 환경변수 또는 같은 상위 폴더 자동 탐색을 사용하고, source가 없으면 저장소 내부 보존본을 사용함 |
| raw -> trainable_windows 생성 | 부분 포함 | `src/third_model/data_io.py`, `data/processed/window_import_metadata.json`, `docs/01_PIPELINE_STEPS.md` | 현재 저장소는 current-best의 `trainable_windows.csv`를 import한 상태이며 raw에서 canonical window를 다시 만드는 전체 코드는 저장소 내부 active flow로 닫혀 있지 않음 | 새 raw 데이터부터 모델 입력까지 재현하려면 raw 압축 해제 구조, canonical 기준, feature 생성 코드, output schema 검증이 필요 |
| missing row 26개 추적 | 포함 | `compare/m1_threshold_weight_rationale_report.ipynb` 섹션 2, `output/reports/row_flow_summary.csv`, `output/reports/key_coverage_by_artifact.csv`, `output/reports/missing_agent_windows.csv` | missing row가 전부 `pre_fault`라는 점은 성능 해석에 계속 같이 표기해야 함 | canonical M1 1252개 중 final agent 1226개. 빠진 26개는 모두 `pre_fault`, split은 train 23개/validation 3개, holdout은 보존 |
| M1-only scope | 포함 | `output/reports/m1_scope_audit.md`, `MODEL_INVENTORY_KO.md`, `compare` notebooks | M2 calibration 수치가 없음 | 현재 검증은 `manufacturer 1` 기준. M2 또는 전체 제조사 일반 성능으로 표현 금지. M2 적용 시 별도 calibration/validation 필요 |
| IF/Mahalanobis threshold | 포함 | `compare/m1_threshold_weight_rationale_report.ipynb` 섹션 4, `output/reports/anomaly_if_mahalanobis_policy_grid.csv` | validation anomaly persistence가 약하므로 anomaly 단독 모델처럼 주장하면 안 됨 | IF 0.90/Mahalanobis 1.00은 holdout FPR guardrail과 early evidence 절충으로 설명 |
| criticality threshold | 포함 | `compare/m1_threshold_weight_rationale_report.ipynb` 섹션 4, `output/reports/anomaly_criticality_threshold_sweep.csv` | `criticality=5`가 anomaly-only metric best는 아님 | 5는 약 30시간 지속 evidence 기준. `criticality=3`은 holdout recall이 더 좋지만 최종 evidence 신뢰도 기준으로 5 선택 |
| risk level applied threshold | 포함 | `compare/m1_threshold_weight_rationale_report.ipynb` 섹션 3/5, `output/reports/risk_level_actual_summary.csv`, `output/reports/risk_threshold_actual_values.csv` | 과거 fallback 설명의 0.44를 현재 active M1 threshold처럼 말하면 안 됨 | 실제 M1 output 기준은 medium 0.22, high 0.92, critical 0.92. high/critical 동일 cutoff라 현재 output에는 high row가 없음 |
| gate threshold | 부분 포함 | `compare/m1_threshold_weight_rationale_report.ipynb` 섹션 7, `output/reports/m1_gate_threshold_sweep.csv`, `output/reports/m1_gate_selected_threshold_summary.csv`, `output/reports/m1_gate_threshold_reference.csv` | task/activity native label이 없어 true performance claim은 불가. fault/pre-event도 standalone alarm optimum은 아님 | fault 0.50, pre-event 0.60은 evidence runtime policy로 설명. FPR<=0.20 대안과 비교하고, task/activity는 산출 필드와 review evidence로만 해석 |
| M1 Specialist 가중치 | 부분 포함 | `compare/m1_threshold_weight_rationale_report.ipynb` 섹션 8, `output/reports/m1_specialist_priority_weight_ablation.csv`, `output/reports/m1_specialist_priority_weight_grid.csv` | 0.55/0.30/0.15가 metric-only best는 아님 | pre-event 중심의 설명 가능한 운영식으로 설명. group-heavy grid 결과는 live inference에서 label-derived risk가 있어 단정 금지 |
| fault_group_weight | 부분 포함 | `compare/m1_threshold_weight_rationale_report.ipynb` 섹션 8, `output/reports/fault_group_weight_summary.csv` | 현재 fault group은 `fault_label` 파생 성격이 강해 하드코딩/label leakage로 보일 수 있음 | live inference에서는 label-free fault group 추론 또는 별도 calibration 필요. 동일 weight baseline과 uniform group 비교는 ablation에 포함 |
| hybrid priority weight | 포함 | `compare/m1_threshold_weight_rationale_report.ipynb` 섹션 11~12, `output/reports/hybrid_weight_sweep.csv`, `output/reports/hybrid_selected_weight_comparison.csv` | 0.65/0.35를 best라고 표현하면 안 됨 | 0.65/0.35는 운영 선택점. 0.72/0.28과 0.90/0.10은 holdout precision/FPR이 같거나 더 좋은 관측 지표가 있음 |
| level calibration FPR cap | 포함 | `compare/m1_threshold_weight_rationale_report.ipynb` 섹션 10, `output/reports/level_calibration_fpr_cap_sweep.csv` | 현재 데이터에서는 cap 0.05~0.20이 모두 같은 threshold로 수렴하므로 cap 효과를 과장하면 안 됨 | `FPR <= 0.20`은 느슨한 threshold를 만든 원인이 아니라 future validation 분포에 대한 운영 상한 guardrail로 설명 |
| agent card 컬럼 계약 | 포함 | `docs/02_AGENT_OUTPUT_CONTRACT.md`, `AGENT_HANDOFF_KO.md`, `output/agent/agent_card_column_groups_ko.md`, `compare/m1_threshold_weight_rationale_report.ipynb` 섹션 2-1 | 최종 hybrid card와 M1 parallel card를 혼동하면 안 됨 | 최종 card는 1226 rows / 55 columns. M1 parallel card는 1252 rows / 29 columns이며 M1-only evidence |
| 성능표 및 시각화 | 포함 | `compare/m1_specialist_performance_comparison.ipynb`, `compare/m1_threshold_weight_rationale_report.ipynb`, `output/reports/*.csv` | raw-level 재생성 그래프와 task/activity true-label 그래프는 없음 | 모델별 비교표, threshold sweep, hybrid sweep, level cap, score/level 변화, coverage plot은 Plotly로 포함 |

# 현재 프롬프트 추가 필요사항

## 반드시 추가할 내용

- 보고서가 실제 파일 기준으로 작성됐는지 확인하라.
- 모델 파일, metadata, score CSV, agent card, report 사이의 key coverage를 확인하라.
- `risk_scores`, `leadtime_scores`, `priority_scores`, `priority_cards` 각각의 missing row를 추적하라.
- M1 canonical 1252개와 final M1 agent 1226개의 차이 26개가 모두 `pre_fault`임을 보고서에 반영하라.
- current-best score bridge가 risk/leadtime 기본 실행 경로라는 점과, risk/leadtime model joblib이 포함됐더라도 새 raw window 재추론은 별도 파이프라인이 필요하다는 점을 구분하라.
- `0.65/0.35` hybrid를 best라고 단정하지 말고 `0.72/0.28`, `0.90/0.10`과 비교하라.
- `fault_group_weight`가 현재 `fault_label` 파생 성격이 강하므로 live inference risk를 명시하라.
- task/activity gate는 native label 부재 때문에 proxy 또는 산출물 확인 수준으로만 설명하라.
- M1 gate 0.50/0.60은 standalone alarm optimum이 아니라 specialist evidence threshold로 설명하라.
- `risk_scores.csv`의 applied threshold 컬럼을 확인하고, 실제 M1 output 기준 0.22/0.92/0.92를 문서에 반영하라.
- 최종 agent card 55 columns와 M1 specialist parallel card 29 columns를 구분해서 설명하라.
- raw -> canonical `trainable_windows.csv` 재생성 파이프라인이 저장소 내부에서 완전히 닫혀 있는지 확인하라.

## 부분적으로 보완할 내용

- 외부 source는 환경변수 또는 같은 상위 폴더 자동 탐색을 사용한다. source가 없으면 저장소 내부 보존본으로 재현 실행한다.
- level calibration의 `FPR <= 0.20`은 현재 sweep에서 threshold 차이를 만들지 않았으므로 운영 guardrail로 설명하라.
- criticality 5는 anomaly recall 최적값이 아니라 persistence evidence 기준으로 설명하라.
- M1 specialist 0.55/0.30/0.15는 metric-only best가 아니라 설명 가능한 운영식임을 명시하라.
- risk high 0.44처럼 보이는 오래된 fallback/중간 설계값은 active M1 output 수치와 분리해서 설명하라.

## 현재 프롬프트에 이미 포함된 내용

- 보고서 포함 여부 점검
- 미포함/부분 포함 항목의 보완 방향 작성
- threshold/weight/level 기준의 선택 근거 정리
- 성능표와 Plotly 시각화 생성
- missing row 26개 coverage 추적
- M1-only scope 명시
- hybrid weight 최적 표현 재검토

# 실험 재실행 필요 항목

| 항목 | 재실행 필요 여부 | 이유 | 예상 산출물 |
|---|---|---|---|
| raw -> canonical trainable_windows 전체 재생성 | 필요 | 현재 저장소는 current-best `trainable_windows.csv` import 구조 | raw inventory, canonical window CSV, feature contract, row coverage report |
| 새 raw window에 대한 risk/leadtime/priority 재추론 | 필요 | risk/leadtime model 파일은 있으나 기본 flow는 score bridge | 재추론된 `risk_scores.csv`, `leadtime_scores.csv`, `priority_scores.csv`, feature compatibility report |
| task/activity gate native-label validation | 필요 | 현재 최종 저장소에는 true task/activity label이 없음 | gate별 precision/recall/FPR/balanced accuracy sweep |
| fault_group_weight label-free 적용성 검증 | 필요 | 현재 group weight는 `fault_label` 파생 성격이 강함 | label-free group inference policy, uniform baseline 비교, leakage audit |
| M2 또는 전체 제조사 calibration | 필요 | 현재 검증은 M1-only | M2 threshold sweep, M2 row coverage, manufacturer별 calibration report |
| external path 제거 후 clean-room rebuild | 필요 | 기본 config가 절대 경로를 포함 | relative/config 기반 run log, standalone smoke test report |
| IF/Mahalanobis threshold sweep | 불필요 | 현재 grid CSV와 Plotly 섹션 생성 완료 | `anomaly_if_mahalanobis_policy_grid.csv` |
| criticality threshold sweep | 불필요 | 현재 1~12 sweep 생성 완료 | `anomaly_criticality_threshold_sweep.csv` |
| hybrid weight sweep | 불필요 | 0.00~1.00 sweep 및 0.65/0.72/0.90 비교 생성 완료 | `hybrid_weight_sweep.csv`, `hybrid_selected_weight_comparison.csv` |
| level calibration FPR cap sweep | 불필요 | 0.05/0.10/0.15/0.20 비교 생성 완료 | `level_calibration_fpr_cap_sweep.csv` |
| risk applied threshold 확인 | 불필요 | `risk_scores.csv`의 applied threshold 컬럼과 level 분포에서 확인 가능 | `risk_level_actual_summary.csv`, `risk_threshold_actual_values.csv` |

# 문서 보완 항목

| 항목 | 보완 위치 | 추가할 내용 |
|---|---|---|
| risk/leadtime 재현 가능성 | `MODEL_INVENTORY_KO.md`, `docs/07_HANDOFF_FILE_INDEX.md` | 모델 파일은 포함됐지만 기본 실행은 score bridge라는 점 |
| 외부 경로 의존성 | `docs/01_PIPELINE_STEPS.md`, `docs/05_RUNBOOK.md` | 정적 보고/열람과 full rebuild 요구사항 분리 |
| raw -> trainable_windows 제한 | `docs/01_PIPELINE_STEPS.md` | raw 재생성 파이프라인은 아직 package-only로 닫혀 있지 않음 |
| missing row 26개 | `compare` notebooks, `docs/07_HANDOFF_FILE_INDEX.md` | 1252 -> 1226, 전부 pre_fault, holdout 보존 |
| M1-only scope | 모든 발표/보고서 요약 | M2 일반화 금지, M2 calibration 필요 |
| hybrid 0.65 표현 | `compare/m1_threshold_weight_rationale_report.ipynb`, 발표본 | best가 아니라 운영 선택점. 0.72/0.90 비교 포함 |
| risk applied threshold | `MODEL_INVENTORY_KO.md`, `AGENT_HANDOFF_KO.md`, `compare/m1_threshold_weight_rationale_report.ipynb` | 실제 M1 output 기준 0.22/0.92/0.92, high row 없음. 0.44는 active threshold로 말하지 않음 |
| fault_group_weight 제한 | `MODEL_INVENTORY_KO.md`, `AGENT_HANDOFF_KO.md` | live inference에서 label-derived risk 검토 필요 |
| gate threshold 제한 | `MODEL_INVENTORY_KO.md`, `AGENT_HANDOFF_KO.md` | 0.50/0.60은 evidence runtime policy. task/activity native label 부재 |

# 추가 제안

- 추가 필요 항목:
  - 발견 근거: `m1_specialist_fault_group`, `m1_specialist_group_weight`가 `fault_label`과 강하게 결합되어 있고, group-only/grid-heavy 후보가 비정상적으로 좋은 성능을 보임.
  - 왜 필요한가: live inference에서 사전에 알 수 없는 label을 쓰는 구조로 보이면 발표 방어가 어렵다.
  - 추가 위치: `MODEL_INVENTORY_KO.md`, `compare/m1_threshold_weight_rationale_report.ipynb`, M1 specialist runtime policy 문서.
  - 코드 수정 필요 여부: 필요. label-free group inference 또는 group weight 제거/축소 운영안을 별도 실험해야 함.

- 추가 필요 항목:
  - 발견 근거: 이전 버전의 `src/third_model/config.py`는 source path 기본값이 특정 로컬 절대경로였다.
  - 왜 필요한가: 저장소를 받은 사람이 다른 PC에서 full rebuild할 때 실패할 수 있다.
  - 추가 위치: `docs/05_RUNBOOK.md`, `docs/01_PIPELINE_STEPS.md`.
  - 코드 수정 필요 여부: 필요. env override만이 아니라 package-local config 예시를 제공해야 함.

- 추가 필요 항목:
  - 발견 근거: task/activity gate에 대한 native target label이 최종 산출물에 없음.
  - 왜 필요한가: threshold 0.5를 성능 기준으로 방어하려면 true label이 필요하다.
  - 추가 위치: `compare/m1_threshold_weight_rationale_report.ipynb`, `MODEL_INVENTORY_KO.md`.
  - 코드 수정 필요 여부: 데이터/라벨 산출 단계 수정 필요.
