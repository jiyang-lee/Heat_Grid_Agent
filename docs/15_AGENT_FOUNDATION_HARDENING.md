# Agent Foundation hardening

## PR 02 변경 맵

PR 02 squash commit은 `c5b1a9e`이며 history는 수정하지 않았다.

| 영역 | 변경 파일 | 핵심 동작 | 전용 회귀 테스트 | 실패 영향 |
|---|---|---|---|---|
| A 외부 웹 검색 제거 | `assessment.py`, `contracts.py`, `graph.py`, `nodes_evidence.py`, backend `automation_routes.py`, `schemas.py` | 외부 검색 상태·resume 입력·graph route·candidate 생성을 코어 실행에서 제거 | `test_agent_request_has_no_external_search_resume_input`, `test_external_search_is_not_a_valid_loop_decision` | 검색 route 재노출, 승인 없는 외부 호출 |
| B 상태 계약 축소 | `state.py`, `nodes_input.py`, `nodes_output.py`, `nodes_completion.py`, `run_models.py` | request/evidence/loop/output/audit/result frozen 모델로 상태 소유권 분리 | `test_state_contract_is_nested_and_frozen`, `test_graph_executes_with_core_ports_only` | checkpoint 역직렬화와 API 결과 조립 실패 |
| C 정책 레지스트리 | `decision_policy.py`, `assessment.py` | 모델 재검증, 내부 RAG, 진단, 사람 검토, 완료 순서 고정 | `test_decision_policy_priority_is_stable`, `test_model_revalidation_precedes_internal_rag` | 반복 순서 변경, 검수 우회 |
| D async 경계 | backend evidence/input/report adapter, `report_nodes.py`, report generator | async I/O는 `ainvoke`, 동기 작업은 AnyIO thread 경계, 보고서 환경변수 전역 변경 제거 | `test_heatgrid_ops_agent_tools.py`, `test_agent_core_ports.py` | event loop 정지, 실행 간 설정 누출 |

## 웹 검색 감사

감사 범위는 agent core, backend route, evidence candidate, approval policy, 설정, README/자동화 문서, frontend 호출 계약이다.

- 코어에는 URL, 도메인, 검색어, generic HTTP, 외부 검색 route가 없다.
- backend 신규 candidate는 `source_type=manual`만 허용하고 query 입력을 거부한다.
- `external_search` action과 task 생성은 항상 거부한다.
- 기존 web/query/external_search DB row는 list/get 응답만 허용한다.
- 운영자 manual evidence 검수와 RAG 적재는 유지한다.
- `external_search` enum은 historical response 역직렬화용 deprecated 값으로 남긴다.
- 프런트 코드는 범위 밖이므로 기존 evidence candidate/승인 UI와 backend의 read-only 정책이 불일치할 수 있다.

## Worker 입력 계약

- card: ID, Substation, manufacturer, priority, 상태, review 여부, reason
- 모델: status, agreement, component 결과, stored/current score, delta, reason
- 날씨: status, 기준 시각, 온도, 습도, 강수, 바람, provenance
- RAG: score 내림차순, evidence ID 오름차순, 최대 5개, chunk당 최대 400 token
- 입력 3,000, 출력 1,000, 총 예약 4,000 token
- 전체 60초, 첫 시도 최대 45초, 재시도 최대 15초
- 날씨 또는 인용 가능한 RAG가 없거나 최소 입력이 상한을 넘으면 모델을 호출하지 않고 사람 검토로 전환

측정 fixture는 `tests/fixtures/diagnostic_input_cases.json`이다.

## DB 소유권

- base/predictor: `001~003` init SQL, `scripts/predictor_db_schema.py`, backend의 기존 ensure 함수
- agent execution: `004_agent_execution.sql`

`002`는 predictor/alert 의존 스키마가 아직 없으면 fresh Docker init에서 defer한다. `004`는 agent base table 없이도 task/ledger를 만들고, server startup 재적용 시 FK와 기존 queued/running task를 보강한다. 두 파일 모두 반복 적용 가능하다.
