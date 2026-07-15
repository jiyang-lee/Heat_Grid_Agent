# 프론트엔드 인계: Replay / Review Chat / Agent Child Run

## 개요

`develop2`에는 백엔드, DB migration, agent runtime 변경만 먼저 반영한다. 프론트엔드는 별도 담당자가 아래 API와 상태 전이를 기준으로 UI를 맞춘다.

## 반영해야 할 API 흐름

| 영역 | 프론트에서 반영할 동작 |
| --- | --- |
| Review Chat Proposal | 채팅 메시지 응답의 `proposal`을 확정 전 상태로 표시한다. proposal 생성만으로는 review가 저장되지 않는다. |
| Proposal Confirm | 운영자 확정 버튼에서 `POST /api/review-chat/proposals/{proposal_id}/confirm`을 호출한다. |
| Child Run | confirm 응답에 `child_run_id`가 있으면 child agent run 상세/상태를 표시한다. |
| Replay | replay feature flag가 꺼져 API가 503을 반환하면 비활성 상태로 표시한다. 활성 환경에서는 tick, window, alert delta를 표시한다. |
| Stage Snapshot | parent/child 모두 9개 stage snapshot이 정상이다. `reused_from_snapshot_id`가 있으면 이전 snapshot 재사용으로 표시한다. |

## Review Chat Confirm 요청

```json
{
  "confirmed_by": "<operator>",
  "idempotency_key": "<unique-key>",
  "expected_proposal_status": "awaiting_confirmation",
  "expected_review_version": 0
}
```

`expected_review_version`은 proposal 응답의 `expected_review_version` 값을 그대로 사용한다.

## Proposal 상태 표시

| 상태 | UI 의미 |
| --- | --- |
| `awaiting_confirmation` | 운영자 확정 또는 취소 가능 |
| `executing` | 확정 실행 중 |
| `executed` | 실행 완료. `child_run_id`가 있으면 child run 연결 |
| `stale` | proposal 생성 이후 review context가 바뀌어 재확인 필요 |
| `expired` | proposal 만료 |
| `conflict` | optimistic concurrency 충돌 |
| `failed` | 실행 실패 |

## DB 변경 타이밍

proposal 생성 전후에는 `agent_run_reviews`가 증가하지 않는다. `confirm` 성공 후에만 parent run review가 저장된다.

실측값:

| 단계 | parent review count |
| --- | ---: |
| proposal 전 | 0 |
| proposal 생성 후, confirm 전 | 0 |
| confirm 후 | 1 |

## Intent 문구 주의

`"RAG 근거 부족으로 거절"`은 현재 백엔드 intent mapping상 다음으로 분류된다.

| 입력 문구 | reason_category | target_stage |
| --- | --- | --- |
| `RAG 근거 부족으로 거절` | `rag_retrieval_issue` | `rag_retrieval` |
| `거절. 보고서 근거 부족으로 거절` | `report_draft_issue` | `report_draft` |

따라서 report 재생성을 유도하는 UI 예시는 RAG가 아니라 보고서/summary/action plan 계열 표현을 사용해야 한다.

## Child report_draft Trace 표시

`report_draft` child run은 snapshot 기반 재생성 경로다. 프론트에서 가능하면 아래 값을 표시한다.

| 필드 | 정상 기준 |
| --- | ---: |
| `agent_model_calls.actual_tool_calls` | 0 |
| `agent_model_calls.actual_model_turns` | 1 이하 |
| `agent_tool_calls` rows for `report_draft` | 0 |
| `execution_profile` | `report_snapshot_only` |
| `snapshot_bundle_hash` | 표시 가능하면 노출 |

## Replay Tick → Window → Alert 표시값

Replay 화면에서 최소한 아래 값을 보여준다.

| 값 | 의미 |
| --- | --- |
| `sequence` | sensor tick 번호 |
| `window_start`, `window_end` | 36 tick 단위 집계 window |
| `result_count` | window model 결과 수. 정상 31 |
| `alert_delta.opened` | 새로 열린 synthetic alert 수 |
| `alert_delta.resolved` | rollover로 resolved 된 alert 수 |
| `synthetic` | replay synthetic alert 여부 |
| `replay_run_id` | replay run 연결 키 |

실측 기준:

| 항목 | 값 |
| --- | ---: |
| 36 tick당 모델 추론 | 1회 |
| window당 result count | 31 |
| high synthetic alert opened | 31 |
| resolved | 0 |

## 프론트에서 확인할 E2E 예시

1. Parent agent run 상세에서 Review Chat thread를 연다.
2. `거절. 보고서 근거 부족으로 거절` 메시지를 보낸다.
3. proposal card가 `awaiting_confirmation`으로 표시되는지 확인한다.
4. confirm 버튼을 누른다.
5. response의 `child_run_id`로 child run 상태를 표시한다.
6. child run 완료 후 stage snapshot 9개와 `report_draft` trace를 확인한다.
7. child run을 `approve`로 운영자 승인한다.

## 백엔드 완료 조건

백엔드는 다음 조건으로 검증됐다.

| 조건 | 결과 |
| --- | --- |
| DB migration verify | 통과 |
| focused regression | 32 passed |
| ruff | 통과 |
| basedpyright | 통과 |
| Child report_draft tool calls | 0 |
| Child report_draft model turns | 0 measured, 1 이하 |
