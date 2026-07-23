# final_test 시연 운영 가이드

## 시연 경로

`final_test` 시연 문서 생성·수정 흐름에서는 OpenAI 모델을 호출하지 않는다. 알림 화면은 `/api/final-test/packages`에서 알림과 `demo_id`의 관계만 읽고, 선택 후 `/api/final-test/packages/{demo_id}`를 조회한다. 이 응답에 고장 전 센서값, 고장 센서값, 우선순위, 작업지시서 v1·v2·v3, 보고서 v1·v2·v3와 챗봇 대본이 모두 들어 있다.

챗봇은 가드레일을 먼저 검사한다. 준비된 수정 질문은 `chat_script`에서 저장된 v2 또는 v3를 즉시 미리보기하고, 사용자가 `수정` 버튼을 누른 뒤에만 현재 버전으로 전환한다. 이 경로는 API 키가 없어도 동작하며 모델 지연의 영향을 받지 않는다.

준비되지 않은 일반 운영 질문은 `/api/final-test/packages/{demo_id}/chat`에서 현재 설정의 `HEATGRID_NATURAL_CHAT_MODEL`을 사용한다. 모델에는 선택한 기계실의 저장 스냅샷, 현재 문서 버전, 최근 대화만 전달한다. 다른 기계실·업무 외 질문, 프롬프트 공격, 안전 절차 우회는 답변 전에 차단한다. 모델 답변은 설명 전용이며 문서를 생성·수정·승인하지 않는다. API 키가 없거나 모델 호출이 실패하면 현재 기계실 범위 안내로 즉시 대체한다.

시연용 준비 질문은 다음과 같다.

1. `현재 가장 큰 위험은 무엇인가요?`
2. `작업목적의 내용을 세부적으로 바꿔줘` → 작업지시서 v2
3. `안전확인 내용을 현장 기준으로 보강해줘` → 작업지시서 v3
4. `조치 결과를 세부적으로 작성해줘` → 보고서 v2
5. `결론과 후속 점검 내용을 구체적으로 바꿔줘` → 보고서 v3

## GPT-5.4 상위 모델 루프를 별도로 호출하는 방법

상위 모델은 시연이 아닌 검증 환경에서만 사용한다. 현재 코드는 `HEATGRID_REJUDGE_MODEL`을 `AgentRuntime.rejudge_model`에 주입하며, 다음 두 경로가 같은 모델을 사용한다.

1. `ml_validation.quality_status`가 `insufficient` 또는 `unavailable`이면 `higher_model_reassessment` 단계가 자동 호출된다.
2. 운영자 검토에서 `reason_category=escalation_issue`, `next_action=targeted_rerun`을 제출하면 상위 모델 재판단 단계만 자식 실행으로 다시 호출한다.

먼저 계정에서 사용할 수 있는 정확한 모델 ID인지 확인한다. 응답에 `gpt-5.4`가 없으면 그 계정에 표시된 다른 모델 ID를 사용한다.

```bash
curl https://api.openai.com/v1/models/gpt-5.4 \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

루트 `.env` 또는 실행 환경에 다음 값을 둔 뒤 백엔드를 다시 만든다.

```dotenv
OPENAI_API_KEY=...
HEATGRID_REJUDGE_MODEL=gpt-5.4
HEATGRID_ANSWER_QUALITY_ENABLED=true
```

```bash
docker compose up -d --build heatgrid-backend
curl http://127.0.0.1:8003/api/agent-models
```

완료된 일반 에이전트 실행을 상위 모델 단계로만 다시 보내려면 현재 `review_version`을 확인한 후 다음 요청을 보낸다.

```bash
curl -X POST http://127.0.0.1:8003/api/agent-runs/RUN_ID/reviews \
  -H "Content-Type: application/json" \
  -d '{
    "expected_review_version": 0,
    "idempotency_key": "manual-gpt54-rejudge-001",
    "decision": "correct",
    "reviewer": "operator",
    "reason": "상위 모델로 판단을 다시 확인",
    "reason_category": "escalation_issue",
    "next_action": "targeted_rerun",
    "disposition": "urgent_review",
    "correction": {"instruction": "저장된 단계 스냅샷만 사용해 재판단"}
  }'
```

응답의 `child_run_id`, `routing_status=scheduled`, `target_stage=higher_model_reassessment`를 확인한다. 이 호출은 실제 비용과 지연이 발생하므로 `final_test` 발표 흐름에서는 실행하지 않는다.

모델 목록과 개별 모델 조회 계약은 [OpenAI Models API](https://platform.openai.com/docs/api-reference/models/object?lang=curl)를 기준으로 한다.
