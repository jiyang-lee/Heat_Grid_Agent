# HeatGrid M1 Specialist 모델 저장소

`agent/mlmodel` 브랜치는 `manufacturer 1` 기준 HeatGrid 모델 산출물을 재현하고, 최종 agent card까지 생성하는 실행 저장소다.

이 저장소는 두 가지 용도로 정리되어 있다.

| 목적 | 실행 방식 | 설명 |
|---|---|---|
| 전달본 재현 | `--steps all` | GitHub에서 받은 상태 그대로 최종 card를 다시 생성 |
| 원천 재학습 | `--steps full_retrain` | current-best와 M1 specialist를 현재 저장소 입력으로 다시 학습한 뒤 산출물 갱신 |

## Quick Start

```powershell
uv sync
uv run python --version
uv run third-model-pipeline --steps all
uv run python -m unittest discover -s tests -v
```

기준 Python은 `.python-version`의 `3.12`다. `uv run python --version` 결과가 3.12 계열이면 된다.

## 저장소 구조

| 폴더 | 역할 |
|---|---|
| `simulator/` | PostgreSQL 기반 운영 보조 API 서버와 시뮬레이션 |
| `frontend/` | 프론트 프로토타입과 세종 1생활권 지도 데이터 |
| `scripts/` | DB 적재, notebook 생성, 파이프라인 보조 스크립트 |
| `src/` | 모델 파이프라인 패키지 코드 |
| `data/` | 처리 데이터 |
| `models/` | 학습된 모델 산출물 |
| `artifacts/` | 모델 메타데이터와 실험 산출물 |
| `output/` | 최종 card, score, report 산출물 |
| `docs/` | 모델, 운영, API 문서 |
| `docs/handoff/` | 인계 문서 |
| `docs/model/` | 모델 범위와 인벤토리 문서 |
| `docs/package/` | 패키지 사용 및 구성 문서 |
| `docs/report/` | 의사결정, 검증, 계약 보고서 |
| `tests/` | 재현성, API, DB 계약 테스트 |

## 최종 산출물

| 파일 | 역할 | rows | columns |
|---|---|---:|---:|
| `output/agent_priority_card.csv` | agent/API/UI가 우선 읽는 공식 card | 1252 | 55 |
| `output/agent/m1_agent_priority_card.csv` | 공식 card 복사본 | 1252 | 55 |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 specialist 단독 병렬 evidence card | 1252 | 29 |

공식 `priority_score`는 M1 hybrid priority다.

```text
priority_score
= 0.65 * current_best_priority_score
+ 0.35 * m1_specialist_priority_score
```

`0.65 / 0.35`는 모든 metric의 절대 최적값이 아니라, current-best baseline 유지와 M1 specialist 반영률을 같이 본 운영 선택점이다. 비교 근거는 `compare/m1_threshold_weight_rationale_report.ipynb`와 `output/reports/hybrid_selected_weight_comparison.csv`에 있다.

## 실행 모드

### 1. 저장소 단독 재현

```powershell
uv run third-model-pipeline --steps all
```

source 프로젝트가 없어도 저장소 내부 보존 산출물을 사용해 최종 card를 재생성한다.

```text
raw -> windows -> model_artifacts -> anomaly -> best_scores -> merge
-> agent_card -> m1_specialist_gates -> m1_specialist -> validation
```

### 2. 원천 재학습 포함 전체 재생성

```powershell
uv run third-model-pipeline --steps full_retrain
```

원천 프로젝트가 같은 상위 폴더에 있거나 환경변수로 지정되어 있어야 한다.

```text
raw -> windows -> model_artifacts -> anomaly -> retrain_current_best -> merge -> agent_card
-> retrain_m1_specialist
-> m1_specialist_gates -> m1_specialist -> validation
```

개별 재학습도 가능하다.

```powershell
uv run third-model-pipeline --steps retrain_current_best
uv run third-model-pipeline --steps retrain_m1_specialist
```

## Source 탐색

코드는 외부 절대경로를 고정하지 않는다. 환경변수가 있으면 우선 사용하고, 없으면 저장소와 같은 상위 폴더를 자동 탐색한다.

| 변수 | 역할 | 기본 탐색 후보 |
|---|---|---|
| `THIRD_MODEL_SOURCE_BEST_ROOT` | current-best source root | `../HeatGrid_Agent/best` |
| `THIRD_MODEL_CURRENT_BEST_PYTHON` | current-best source 재학습 Python | `../HeatGrid_Agent/.venv/Scripts/python.exe` |
| `THIRD_MODEL_3RD_PROJECT_ROOT` | M1 specialist training-input bootstrap/external source root | `../3rd_project_for_ML-main/3rd_project_for_ML-main` |
| `THIRD_MODEL_M1_SPECIALIST_PYTHON` | legacy external M1 specialist 재학습 Python | 현재 uv Python |
| `THIRD_MODEL_PREDIST_ZIP_PATH` | 첫 M1 training-input bootstrap용 PreDist zip | `../HeatGrid_Agent/data/_downloads/predist_dataset.zip` |

M1 source 재학습은 source 폴더 안 `05_데이터셋/PreDist/predist_dataset.zip`을 요구한다. 없으면 위 zip 후보를 찾아 source 폴더로 복사한다.

## 문서 지도

| 먼저 볼 파일 | 역할 |
|---|---|
| `docs/README.md` | 전체 문서 지도와 읽는 순서 |
| `docs/package/PACKAGE_README_KO.md` | 저장소 사용 안내 |
| `docs/handoff/HANDOFF.md` | 짧은 인계 요약 |
| `docs/handoff/M1_SPECIALIST_HANDOFF_KO.md` | M1 specialist 중심 인계 |
| `docs/model/MODEL_INVENTORY_KO.md` | 모델 파일, score, 재학습 책임 정리 |
| `docs/package/PACKAGE_MANIFEST.md` | 포함 파일 전체 목록 |
| `docs/05_RUNBOOK.md` | 실행/검증 명령 |
| `docs/07_HANDOFF_FILE_INDEX.md` | 받는 사람이 볼 파일 색인 |

## 보고/발표 자료

| 파일 | 내용 |
|---|---|
| `compare/m1_specialist_performance_comparison.ipynb` | 최종본 도출 과정과 모델 후보 비교 |
| `compare/m1_threshold_weight_rationale_report.ipynb` | threshold, weight, hybrid 선택 근거 |
| `output/reports/final_validation_report.md` | 최종 검증 요약 |
| `docs/08_MODEL_REPORT_DEFENSE_AUDIT.md` | 보고서 방어 체크리스트 |

## 핵심 해석 제한

- 현재 검증 범위는 M1이다. M2나 전체 제조사 성능으로 일반화하지 않는다.
- 내부 `full_retrain` 기준 최종 card는 M1 canonical window 1252개 전체를 보존한다. 예전 보존 score bridge의 partial coverage 해석은 legacy 비교 맥락에서만 사용한다.
- anomaly는 정상 분포 이탈 evidence다. 단독 fault classifier로 설명하지 않는다.
- leadtime은 정확한 고장 시각 예측값이 아니라 priority 참고 신호다.
- priority는 점검 우선순위 ranking 신호이며 자동 정비 지시가 아니다.

## 공개 전 확인

```powershell
uv run python -m unittest discover -s tests -v
uv run third-model-pipeline --steps all
git status --short
```
# 2026-07-08 Internal Full Retrain Update

- `--steps full_retrain` now runs inside this repository by default. It no longer requires sibling source folders for the current-best risk/leadtime/priority body.
- Internal `full_retrain` order is `raw -> windows -> model_artifacts -> anomaly -> retrain_current_best -> merge -> agent_card -> retrain_m1_specialist -> m1_specialist_gates -> m1_specialist -> validation`.
- Internal current-best regeneration writes `output/risk_scores.csv`, `output/leadtime_scores.csv`, and `output/priority_scores.csv` for all 1252 M1 canonical windows.
- M1 specialist internal mode now trains the fault/task/activity/pre-event gate joblibs from package-local inputs under `artifacts/m1_specialist/training_inputs/`.
- If those M1 training inputs are missing, the first internal retrain can bootstrap them from `THIRD_MODEL_3RD_PROJECT_ROOT`; after that, retrain works with that external path unavailable.
- To force the old external wrappers, set `THIRD_MODEL_CURRENT_BEST_RETRAIN_MODE=external` and/or `THIRD_MODEL_M1_SPECIALIST_RETRAIN_MODE=external`.
