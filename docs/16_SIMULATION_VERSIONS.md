# 16. 시뮬레이션 버전 비교 (v1 vs v2)

`simulator/versions/` 아래 버전 이력이 v1/v2/v3/v4처럼 여러 개로 언급되어 혼동이 있었다. 이 문서는 실제로 무엇이 존재하고 무엇이 현재 사용 중인지 정리한다.

## 결론

- 현재 저장소(`develop2`)의 `simulator/versions/`에는 **`v2_postgres_react_ops` 하나만 존재한다.**
- `v1_langgraph_react_ops`는 `origin/agent/simulation` 브랜치에만 있고, `develop2`에 **병합된 적이 없다.** `simulator/VERSIONING.md`에 "`agent/simulation` 브랜치는 머지하지 않고 보존한다"고 명시돼 있다.
- "v3", "v4"는 `simulator/versions/`의 폴더가 아니라 과거 브랜치/PR 명명 규칙(`backend/v3_langgraph_agent_runner` 등)이며, 시뮬레이터 버전과는 무관하다. 실체가 없으므로 비교 대상이 아니다.

## v1_langgraph_react_ops (미병합, `origin/agent/simulation` 브랜치 전용)

| 항목 | 내용 |
|---|---|
| 목적 | `card_id` 1건 기준 데모. LLM이 직접 읽는 입력 JSON을 만들고 LangGraph ReAct agent가 운영 메모 생성 |
| 진입점 | `POST /api/simulate/{card_id}` |
| 데이터 원천 | 파일 기반 JSON (`contracts/ops_agent_llm_input.schema.json`), DB 연동 없음 |
| 툴 | `get_ops_input(card_id)`, `get_priority_rule()` (2개) |
| 출력 | `summary` / `action_plan` / `caution` |
| Fallback | `OPENAI_API_KEY` 없으면 로컬 규칙 기반 출력으로 대체 (키 없이 데모/테스트 가능) |
| 명시적 제외 범위 | weather API, 운영 문서 RAG, 원본 raw 센서 시계열 전체 적재, 멀티턴 대화 상태 저장 |
| 규모 | README + contracts + examples, 5개 파일 (백엔드 서버 코드 없음) |

## v2_postgres_react_ops (현재 버전, `simulator/versions/`에 존재)

| 항목 | 내용 |
|---|---|
| 목적 | PostgreSQL 기반 운영 보조 API 서버. 우선순위 카드/알림/agent run/검수/재학습까지 전체 운영 루프 커버 |
| 진입점 | `uv run python simulator/versions/v2_postgres_react_ops/backend/server.py` → `http://127.0.0.1:8003` |
| 데이터 원천 | PostgreSQL (`HEATGRID_DATABASE_URL`), replay 데이터셋(`replay_routes.py`) 포함 |
| API 계약 | `/api/alerts`, `/api/agent-runs`, `/api/review-tasks`, `/api/evidence-candidates`, `/api/automation-policy`, `/api/retrain-jobs`, `/api/model-candidates` 등 |
| 규모 | 196개 파일, 약 2.2MB (agent 실행/검수/재학습/lineage 등 리포지토리 다수) |
| 실행 주체 | `Dockerfile.backend`가 이 경로를 `WORKDIR`로 지정, `docker-compose.yml`이 빌드/실행 |
| 참조 문서 | 루트 `README.md`, `AGENTS.md`가 이 경로만 명시 |

### 중요 발견: v2 README가 구식 시드 스크립트를 "기본 적재"로 안내하고 있음

`simulator/versions/v2_postgres_react_ops/README.md`의 "데이터 적재 명령" 섹션에 다음이 **기본(default) 절차**로 문서화돼 있다.

```text
기본 적재: uv run python scripts/simulate_predictor_db.py
```

이 스크립트가 바로 2014~2020년대 구(舊) 모델 학습/평가용 데이터를 `windows`/`priority_evaluation_results` 등에 적재하는 스크립트다. 즉 지금 replay와 뒤섞여 보이는 2020년 데이터는 우연한 잔존물이 아니라, **v2의 공식 문서가 안내하는 기본 부트스트랩 경로 자체가 replay-only 정책과 충돌**하고 있는 것이다. 이 부분은 DB 정리 작업과 함께 README 안내도 같이 갱신해야 한다.

## 정리 방향

1. 코드 정리 대상은 없다 (v1은 애초에 이 브랜치에 없음, v3/v4는 실체가 없음).
2. `simulator/versions/v2_postgres_react_ops/README.md`의 "데이터 적재 명령" 섹션을 replay 기준으로 갱신 필요 (별도 작업, 팀 논의 후 진행).
3. `simulator/VERSIONING.md`는 이 문서를 참조하도록 링크만 추가한다.
