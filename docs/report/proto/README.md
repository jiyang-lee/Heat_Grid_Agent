# proto 한 사이클 — 단계별 보고서

`proto` 브랜치에서 `데이터 → 머신러닝 → priority → LLM/tool → 서버 → 프론트` 를 실DB·실 ML output 없이 **목 데이터로 end-to-end 1바퀴** 돌린 프로토타입의 보고서다. **커밋(=단계) 하나당 보고서 1개**로 쪼갰고, 각 보고서 안에 그 단계의 다이어그램을 넣었다.

![전체 개요](img/00_overview.svg)

## 단계별 보고서 (커밋 순)

| 단계 | 커밋 | 보고서 | 핵심 |
|---|---|---|---|
| S0 자산 이전 | `43e2772` | [01_asset_transfer.md](01_asset_transfer.md) | agent1·mlmodel1 자산 이전 |
| A 계약 | `04b5d41` | [02_contract.md](02_contract.md) | priority 계약 + 목데이터 + 검증 게이트 |
| B 모델 | `3e5092d` | [03_model.md](03_model.md) | LGBM 회귀 학습/평가, rule v2 대비 |
| C 에이전트 | `fad501b` | [04_agent.md](04_agent.md) | langgraph 에이전트, 보고서/메일 초안 |
| D 서버/프론트 | `2fe5d81` | [05_serve.md](05_serve.md) | FastAPI + React/Vite |
| V 검증 | `4143cd1` | [06_validate.md](06_validate.md) | 한 사이클 재현 |
| F 버그픽스 | `8c1b3a5` | [07_bugfix.md](07_bugfix.md) | 키 충돌 + PK 유니크 |

> 참고: 커밋은 위 7개 + 본 보고서 커밋. "feat/fix"만 세면 5개(A·B·C·D·F), 자산이전·검증을 포함하면 7개다.

## 정량 종합
| 항목 | 값 |
|---|---|
| 목 데이터 | 300행 × 25컬럼 (정상 161 / 고장전조 139) |
| 학습 분할 | train 196 / holdout 104 (정답 R=44) |
| 모델 | LightGBM 회귀, 7피처 → 0~100, `priority_v3_lgbm_reg` |
| 성능(holdout) | precision@10/20/44 = 1.00, NDCG = 1.00 → rule v2 동등 이상 채택 |
| priority_scores | 300행 (urgent 65 / high 38 / medium 36 / low 161) |
| 에이전트 산출 | 보고서 5 + 메일 5 |
| 서버 | REST 3 엔드포인트(읽기 전용) |
| 검증 | JSON Schema 6 · DDL 7 · PK 유니크 · pytest 6 passed |

## 1.00 성능 해석 (중요)
목 데이터는 고장전조일수록 위험/이상/임박 신호가 단조적으로 높게 설계돼 정상과 명확히 분리된다. 그래서 LGBM·rule 둘 다 상위권을 완벽히 맞춰 **동률(1.00)** 이 나온다. 즉 1.00은 "데이터가 쉽다"는 뜻이며, 본 사이클의 가치는 **① 끊김 없는 파이프라인 골격, ② 회귀모델이 운영 rule을 대체할 수 있는 평가 프레임, ③ 재발을 막는 검증 게이트**에 있다. 실 ML output 전환 시 1.00 미만이 정상이며 그때 LGBM이 rule을 앞서는지가 진짜 채택 근거가 된다.

## 다이어그램 재생성
```bash
uv run python docs/report/proto/_gen_diagrams.py   # img/*.svg 갱신
```
