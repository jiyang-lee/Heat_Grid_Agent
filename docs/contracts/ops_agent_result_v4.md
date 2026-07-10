# Ops Agent Result v4 계약

## 목적

프론트엔드는 agent run 생성 후 `GET /api/agent-runs/{run_id}/result`를 호출해 운영자용 최종 산출물을 받는다. 기존 `ops_output.summary/action_plan/caution`은 v3 호환 필드로 유지하지만, 신규 화면은 v4 결과 계약을 기준으로 구현한다.

## 엔드포인트

- `POST /api/agent-runs`
  - 입력: `{ "alert_id": "..." }`
  - 출력: 기존 `AgentRunResponse`
- `GET /api/agent-runs/{run_id}/result`
  - 완료된 run이면 `OpsAgentResultV4` 반환
  - run이 없으면 `404`
  - run은 있으나 아직 최종 출력이 없으면 `409`

## 스키마

```json
{
  "schema_version": "ops_agent_result.v4",
  "run_id": "string",
  "card_id": "string",
  "headline": "string",
  "situation": "string",
  "evidence": [
    {
      "label": "string",
      "content": "string",
      "source": "postgres | pgvector | jsonl | kma | fallback | manual"
    }
  ],
  "actions": [
    {
      "priority": 1,
      "title": "string",
      "detail": "string"
    }
  ],
  "cautions": ["string"],
  "report": {
    "title": "string",
    "format": "markdown",
    "content": "string"
  }
}
```

## 프론트 사용 기준

- 카드/목록 첫 줄: `headline`
- 상세 상황: `situation`
- 근거 패널: `evidence`
- 작업 지시 목록: `actions`
- 주의 사항: `cautions`
- 보고서 산출물: `report.content`

## 백엔드 생성 기준

- `summary/action_plan/caution`은 더 이상 프론트의 장기 계약으로 보지 않는다.
- RAG, 단지 매핑, 기상, 운영 근거는 새 필드 안에 자연어로 반영한다.
- 내부 구현 용어인 RAG, pgvector, chunk, API 키 같은 표현은 운영자에게 보여주는 문장 본문에 직접 노출하지 않는다.
- 기상 정보는 고장 원인 확정 근거가 아니라 운영 부하 맥락으로만 사용한다.
