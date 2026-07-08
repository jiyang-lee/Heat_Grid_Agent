# 저장소 사용 안내

이 문서는 저장소를 받은 사람이 바로 실행하고 결과를 확인할 수 있도록 정리한 간단 안내서다. 전체 문서 지도는 `docs/README.md`를 먼저 보면 된다.

## 1. 가장 먼저 할 일

```powershell
uv sync
uv run python run_3rd_model_pipeline.py --steps all
uv run python -m unittest discover -s tests -v
```

`all`은 저장소 내부 보존 산출물을 사용해 최종 결과를 재생성한다. 외부 source 프로젝트가 없어도 동작해야 하는 기본 실행 경로다.

## 2. 최종 결과 확인

| 파일 | 역할 | rows | columns |
|---|---|---:|---:|
| `output/agent_priority_card.csv` | 최종 hybrid agent card | 1252 | 55 |
| `output/agent/m1_agent_priority_card.csv` | 최종 hybrid card 복사본 | 1252 | 55 |
| `output/agent/m1_specialist_parallel_agent_card.csv` | M1 단독 병렬 evidence card | 1252 | 29 |

최종 agent가 우선 읽는 값은 `priority_score`, `priority_level`, `review_required`, `review_reasons`, `trust_level`, `why_reason`, `recommended_action`이다.

## 3. 원천 재학습까지 실행

```powershell
uv run python run_3rd_model_pipeline.py --steps full_retrain
```

`full_retrain`은 다음 순서로 실행된다.

```text
1. current-best source에서 risk/leadtime/priority 계열 재학습
2. risk_model_best.joblib, leadtime_model_best.joblib, priority metadata 갱신
3. M1 canonical windows와 current-best score 연결
4. M1 anomaly, merge, agent card 생성
5. 현재 저장소의 M1 training inputs에서 fault/task/activity/pre-event gate joblib 재학습
6. M1 specialist 모델 산출물 갱신
7. 최종 hybrid priority와 validation 산출
```

## 4. Source 경로 지정

기본 자동 탐색 후보:

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

## 5. 받는 사람이 볼 문서

| 문서 | 역할 |
|---|---|
| `README.md` | 전체 개요와 quick start |
| `docs/README.md` | 문서 지도 |
| `HANDOFF.md` | 짧은 인계 요약 |
| `M1_SPECIALIST_HANDOFF_KO.md` | M1 specialist 인계 |
| `MODEL_INVENTORY_KO.md` | 모델 파일과 재학습 책임 |
| `PACKAGE_MANIFEST.md` | 저장소 구성 목록 |
| `docs/05_RUNBOOK.md` | 실행 명령 모음 |
| `output/reports/final_validation_report.md` | 최종 검증 요약 |
| `compare/m1_threshold_weight_rationale_report.ipynb` | 수치 선택 근거 |

## 6. 주의할 해석

- 현재 검증은 M1 전용이다.
- M1 specialist parallel card는 최종 ordering contract가 아니라 evidence 확인용이다.
- 내부 `full_retrain` 기준 final card는 canonical 1252개 전체를 보존한다.
- `0.65 / 0.35` hybrid는 운영 선택점이지 모든 metric의 절대 최적값이 아니다.
# 2026-07-08 Internal Full Retrain Update

- `uv run python run_3rd_model_pipeline.py --steps full_retrain` is now self-contained by default.
- Current-best risk/leadtime/priority outputs are regenerated from the packaged M1 windows inside this repository.
- M1 specialist fault/task/activity/pre-event gate joblibs are regenerated from package-local training inputs under `artifacts/m1_specialist/training_inputs/`.
- The first internal M1 retrain can bootstrap those inputs from `THIRD_MODEL_3RD_PROJECT_ROOT`; after the inputs exist, the external source path is no longer required.
- The final hybrid agent card now keeps the full 1252-row M1 canonical coverage when using internal full retrain.
- Use `THIRD_MODEL_CURRENT_BEST_RETRAIN_MODE=external` and `THIRD_MODEL_M1_SPECIALIST_RETRAIN_MODE=external` only when you explicitly want the legacy sibling-project wrappers.
