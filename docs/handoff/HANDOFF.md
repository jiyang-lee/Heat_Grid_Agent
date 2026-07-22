# Handoff Summary

이 저장소는 M1 기준 HeatGrid 모델/agent 산출물 전달본이다. 받는 사람은 `uv`로 기본 실행을 재현하고, 필요할 때만 원천 source 재학습을 실행하면 된다.

## 핵심 결론

| 항목 | 값 |
|---|---|
| 검증 scope | `manufacturer 1` |
| 공식 agent card | `output/agent_priority_card.csv` |
| 공식 card 복사본 | `output/agent/m1_agent_priority_card.csv` |
| 공식 card 크기 | 1252 rows / 67 columns |
| M1 병렬 evidence card | `output/agent/m1_specialist_parallel_agent_card.csv` |
| 병렬 card 크기 | 1252 rows / 29 columns |
| 최종 priority | `restored Risk >= 0.78 OR pre-event >= 0.99` gate v4 |

## 바로 실행

```powershell
uv sync
uv run third-model-pipeline --steps all
uv run python -m unittest discover -s tests -v
```

원천 current-best와 M1 specialist까지 다시 학습하려면:

```powershell
uv run third-model-pipeline --steps full_retrain
```

## 읽는 순서

| 순서 | 파일 | 용도 |
|---:|---|---|
| 1 | `README.md` | 전체 개요와 실행 모드 |
| 2 | `docs/README.md` | 문서 지도 |
| 3 | `docs/package/PACKAGE_README_KO.md` | 사용 안내 |
| 4 | `docs/model/MODEL_INVENTORY_KO.md` | 모델 파일과 책임 경계 |
| 5 | `docs/02_AGENT_OUTPUT_CONTRACT.md` | agent card 컬럼 계약 |
| 6 | `docs/05_RUNBOOK.md` | 실행/검증 명령 |
| 7 | `docs/07_HANDOFF_FILE_INDEX.md` | 파일 색인 |
| 8 | `compare/m1_threshold_weight_rationale_report.ipynb` | threshold/weight 근거 |
| 9 | `output/reports/final_validation_report.md` | 최종 검증 요약 |

## 발표 시 주의 문장

- 이 결과는 M1 검증 결과이며 M2 일반 성능으로 말하지 않는다.
- M1 parallel card 1252 rows / 29 columns는 evidence 확인용이고, 최종 agent card는 1252 rows / 67 columns다.
- 빠진 26개 window는 모두 `pre_fault`이며 coverage 보고서에서 별도로 추적한다.
- anomaly는 정상 이탈 근거이고, risk/leadtime/priority를 대체하지 않는다.
- 공식 정책 v4는 `restored Risk >= 0.78 OR pre-event >= 0.99`인 label-free gate다.
- holdout Precision 83.6%, Recall 72.7%, F1 77.8%, FPR 10.4%, 이벤트 7/8이며 이전 v3, 요청 v2, legacy v1은 비교·rollback 값으로 보존한다.
