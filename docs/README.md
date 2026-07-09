# 문서 지도

이 폴더는 M1 specialist 모델 저장소를 설명하는 문서 묶음이다. 처음 받는 사람은 아래 순서대로 읽으면 된다.

## 추천 읽기 순서

| 순서 | 문서 | 목적 |
|---:|---|---|
| 1 | `../README.md` | 전체 개요, quick start, 최종 산출물 |
| 2 | `handoff/HANDOFF.md` | 짧은 인계 요약 |
| 3 | `package/PACKAGE_README_KO.md` | 저장소 사용 안내 |
| 4 | `00_SOURCE_TRACE.md` | source 프로젝트 탐색과 파일 출처 |
| 5 | `01_PIPELINE_STEPS.md` | 실행 step과 row coverage 흐름 |
| 6 | `02_AGENT_OUTPUT_CONTRACT.md` | 최종 agent card 컬럼 계약 |
| 7 | `03_MODEL_DESIGN.md` | anomaly/risk/leadtime/priority 설계 |
| 8 | `04_VALIDATION_AND_ABLATION.md` | 검증, threshold, ablation 산출물 |
| 9 | `05_RUNBOOK.md` | 실행 명령, 재학습, 공개 전 확인 |
| 10 | `06_FINAL_RESULTS.md` | 최종 결과와 해석 |
| 11 | `07_HANDOFF_FILE_INDEX.md` | 받는 사람에게 넘길 파일 색인 |
| 12 | `08_MODEL_REPORT_DEFENSE_AUDIT.md` | 발표/보고서 방어 체크리스트 |
| 13 | `09_CODEX_MODEL_REPORT_REVIEW_PROMPT.md` | 보고서 재검토용 작업 프롬프트 |
| 14 | `11_SERVICE_RAG_LOGGING_AND_CONTEXT.md` | RAG, pgvector, 운영 로그, 세종/기상 문맥 서비스화 |
| 15 | `12_AGENT_RAG_CURRENT_HANDOFF.md` | 현재 Agent/RAG 구성과 추후 모델 서버 연동 인수인계 |
| 16 | `13_BACKEND_V3_RAG_UPLOAD_PREP.md` | backend/v3_rag 업로드 전 충돌 요인과 정리 기준 |

## 목적별 바로가기

### 실행만 하고 싶을 때

```text
../README.md
05_RUNBOOK.md
```

### 최종 agent card를 연결할 때

```text
02_AGENT_OUTPUT_CONTRACT.md
handoff/AGENT_HANDOFF_KO.md
../output/agent/agent_card_column_groups_ko.md
../output/agent/agent_card_value_mapping_ko.md
```

### 발표/보고서 수치 근거를 볼 때

```text
04_VALIDATION_AND_ABLATION.md
06_FINAL_RESULTS.md
08_MODEL_REPORT_DEFENSE_AUDIT.md
../compare/m1_specialist_performance_comparison.ipynb
../compare/m1_threshold_weight_rationale_report.ipynb
```

### 재학습과 traceability를 볼 때

```text
00_SOURCE_TRACE.md
01_PIPELINE_STEPS.md
05_RUNBOOK.md
model/MODEL_INVENTORY_KO.md
package/PACKAGE_MANIFEST.md
```


### RAG/외부 문맥/운영 로그를 볼 때

```text
11_SERVICE_RAG_LOGGING_AND_CONTEXT.md
12_AGENT_RAG_CURRENT_HANDOFF.md
13_BACKEND_V3_RAG_UPLOAD_PREP.md
../data/README.md
```
## 핵심 파일 요약

| 파일 | 설명 |
|---|---|
| `../output/agent_priority_card.csv` | agent가 우선 읽는 공식 card |
| `../output/agent/m1_agent_priority_card.csv` | 공식 card 복사본 |
| `../output/agent/m1_specialist_parallel_agent_card.csv` | M1 specialist 병렬 evidence card |
| `../output/reports/final_validation_report.md` | 최종 검증 요약 |
| `../output/reports/key_coverage_by_artifact.csv` | artifact별 key coverage |
| `../output/reports/missing_agent_windows.csv` | final card에서 빠진 26개 window |
| `../models/risk/risk_model_best.joblib` | current-best risk 모델 본체 |
| `../models/leadtime/leadtime_model_best.joblib` | current-best leadtime 모델 본체 |
| `../models/priority/priority_engine_best_metadata.json` | current-best priority metadata |
| `../models/m1_specialist/` | M1 specialist gate 모델 |

## 문서 작성 원칙

- 현재 검증 범위는 M1로 명시한다.
- `0.65 / 0.35` hybrid를 metric-best라고 단정하지 않는다.
- threshold와 level 값은 비교 실험 산출물에 근거해 설명한다.
- final card와 M1 parallel evidence card를 섞어 말하지 않는다.
- raw에서 canonical window까지 완전히 닫힌 재생성 범위와, current-best source가 담당하는 범위를 구분한다.
