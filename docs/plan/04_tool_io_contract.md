# Tool I/O 계약 문서

## 1. 목적

이 문서는 Agent A가 `ingest_normalize_tool`, `predict_adapter_tool`, `decision_tool`의 입출력 계약을 고정하기 위해 작성한다.

이번 단계의 목표는 실제 DB write나 LangGraph 구현이 아니라, **PreDist 기준 mock payload로도 흔들리지 않는 입출력 shape**를 먼저 고정하는 것이다.

## 2. 공통 원칙

- tool은 DB에 직접 write하지 않는다.
- tool은 DB row-ready payload를 반환한다.
- source별 차이는 input metadata와 adapter에서 흡수한다.
- 모든 tool 출력은 현재 DB 스키마와 1:1로 매핑 가능해야 한다.
- 실패 시 예외만 던지지 말고, 구조화된 실패 payload도 정의한다.

## 3. PreDist mock 기준

- source type: `predist`
- source dataset: `PreDist`
- 기본 단위: `substation_id + observed_at`
- optional time window: `window_start`, `window_end`

### 3.1 raw row 예시

```json
{
  "timestamp": "2020-03-18T11:11:00+00:00",
  "outdoor_temperature": 7.2,
  "p_hc1_return_temperature": 41.8,
  "p_net_meter_flow": 2.1
}
```

### 3.2 ML output mock 예시

```json
{
  "substation_id": 24,
  "timestamp": "2020-03-18T11:11:00+00:00",
  "prediction_label": "anomaly",
  "anomaly_score": 0.82,
  "confidence": 0.91,
  "severity": "high",
  "fault_label": "pump failure",
  "predicted_series": [],
  "estimated_lead_time": "6h"
}
```

## 4. ingest_normalize_tool

### 4.1 역할

- raw 센서 입력을 받는다.
- `raw_sensor_events`용 payload를 만든다.
- `normalized_sensor_features`용 payload를 만든다.

### 4.2 입력

```json
{
  "source_type": "predist",
  "source_dataset": "PreDist",
  "schema_version": "1.0.0",
  "substation_id": "24",
  "site_id": null,
  "asset_id": null,
  "observed_at": "2020-03-18T11:11:00+00:00",
  "window_start": null,
  "window_end": null,
  "raw_payload": {
    "timestamp": "2020-03-18T11:11:00+00:00",
    "outdoor_temperature": 7.2,
    "p_hc1_return_temperature": 41.8,
    "p_net_meter_flow": 2.1
  },
  "feature_context": {
    "manufacturer": "m2",
    "feature_set": "operational_data",
    "row_source": "substation_24.csv"
  }
}
```

### 4.3 출력

```json
{
  "success": true,
  "message": "정규화가 완료되었습니다.",
  "data": {
    "raw_event": {
      "raw_event_id": "raw-24-20200318T111100Z",
      "source_type": "predist",
      "source_dataset": "PreDist",
      "substation_id": "24",
      "observed_at": "2020-03-18T11:11:00+00:00",
      "raw_payload": {},
      "created_at": "2026-06-23T00:00:00+00:00",
      "site_id": null,
      "asset_id": null,
      "schema_version": "1.0.0",
      "metadata": {
        "manufacturer": "m2",
        "row_source": "substation_24.csv"
      }
    },
    "normalized_feature": {
      "feature_id": "feat-24-20200318T111100Z",
      "raw_event_id": "raw-24-20200318T111100Z",
      "substation_id": "24",
      "observed_at": "2020-03-18T11:11:00+00:00",
      "feature_values": {
        "outdoor_temperature": 7.2,
        "p_hc1_return_temperature": 41.8,
        "p_net_meter_flow": 2.1
      },
      "created_at": "2026-06-23T00:00:00+00:00",
      "site_id": null,
      "asset_id": null,
      "schema_version": "1.0.0",
      "metadata": {
        "manufacturer": "m2",
        "missing_fields": []
      }
    }
  }
}
```

### 4.4 실패 출력

```json
{
  "success": false,
  "message": "raw payload에 필수 필드가 부족합니다.",
  "error": "missing_required_raw_fields",
  "data": {
    "missing_fields": [
      "timestamp"
    ]
  }
}
```

### 4.5 DB 매핑

- `raw_event` -> `raw_sensor_events`
- `normalized_feature` -> `normalized_sensor_features`

## 5. predict_adapter_tool

### 5.1 역할

- ML 출력 mock을 받는다.
- canonical prediction contract로 변환한다.
- `model_predictions`용 payload를 만든다.

### 5.2 입력

```json
{
  "feature_id": "feat-24-20200318T111100Z",
  "raw_event_id": "raw-24-20200318T111100Z",
  "source_type": "predist",
  "source_dataset": "PreDist",
  "ml_output": {
    "substation_id": 24,
    "timestamp": "2020-03-18T11:11:00+00:00",
    "prediction_label": "anomaly",
    "anomaly_score": 0.82,
    "confidence": 0.91,
    "severity": "high",
    "fault_label": "pump failure",
    "predicted_series": [],
    "estimated_lead_time": "6h"
  },
  "source_model": "predist_baseline_v1",
  "model_version": "0.1.0"
}
```

### 5.3 출력

```json
{
  "success": true,
  "message": "prediction adapter 변환이 완료되었습니다.",
  "data": {
    "prediction": {
      "prediction_id": "pred-24-20200318T111100Z",
      "feature_id": "feat-24-20200318T111100Z",
      "event_id": "raw-24-20200318T111100Z",
      "source_type": "predist",
      "source_dataset": "PreDist",
      "schema_version": "1.0.0",
      "substation_id": "24",
      "observed_at": "2020-03-18T11:11:00+00:00",
      "prediction_label": "anomaly",
      "prediction_type": "anomaly",
      "prediction_score": 0.82,
      "confidence": 0.91,
      "severity": "high",
      "fault_label": "pump failure",
      "lead_time_hours": 6.0,
      "source_model": "predist_baseline_v1",
      "model_version": "0.1.0",
      "raw_output": {},
      "normalized_output": {},
      "metadata": {
        "predicted_series": []
      },
      "created_at": "2026-06-23T00:00:00+00:00"
    }
  }
}
```

### 5.4 실패 출력

```json
{
  "success": false,
  "message": "ML 출력에서 점수 축을 찾지 못했습니다.",
  "error": "missing_prediction_score_or_confidence",
  "data": {
    "prediction_id": "pred-24-20200318T111100Z"
  }
}
```

### 5.5 매핑 규칙

- `anomaly_score` -> `prediction_score`
- `timestamp` -> `observed_at`
- `estimated_lead_time: "6h"` -> `lead_time_hours: 6.0`
- `predicted_series` -> `metadata.predicted_series`
- ML 원본 전체 -> `raw_output`
- canonical 변환 중간값 -> `normalized_output`

### 5.6 DB 매핑

- `prediction` -> `model_predictions`

## 6. decision_tool

### 6.1 역할

- canonical prediction을 받는다.
- 최소 history context를 같이 받는다.
- `agent_decisions`용 payload를 만든다.

### 6.2 입력

```json
{
  "prediction": {
    "prediction_id": "pred-24-20200318T111100Z",
    "substation_id": "24",
    "prediction_label": "anomaly",
    "prediction_type": "anomaly",
    "prediction_score": 0.82,
    "confidence": 0.91,
    "severity": "high",
    "fault_label": "pump failure",
    "lead_time_hours": 6.0
  },
  "history_context": {
    "recent_fault_count": 1,
    "recent_decision_count": 0
  },
  "decision_context": {
    "rule_version": "team-owned-v1"
  }
}
```

### 6.3 출력

```json
{
  "success": true,
  "message": "decision payload 생성이 완료되었습니다.",
  "data": {
    "decision": {
      "decision_id": "dec-24-20200318T111100Z",
      "prediction_id": "pred-24-20200318T111100Z",
      "substation_id": "24",
      "decision_status": "action_required",
      "decision_summary": "고위험 이상 징후가 감지되어 점검 우선순위 상향이 필요합니다.",
      "recommended_action": "펌프 계통 우선 점검",
      "priority_score": 0.87,
      "priority_rank": 1,
      "reason_codes": [
        "high_severity",
        "fault_label_present",
        "short_lead_time"
      ],
      "operator_note": null,
      "metadata": {
        "recent_fault_count": 1,
        "rule_version": "team-owned-v1"
      },
      "created_at": "2026-06-23T00:00:00+00:00"
    }
  }
}
```

### 6.4 실패 출력

```json
{
  "success": false,
  "message": "prediction 입력이 부족해 review 상태로 반환합니다.",
  "error": "insufficient_prediction_context",
  "data": {
    "decision": {
      "decision_id": "dec-24-20200318T111100Z",
      "prediction_id": "pred-24-20200318T111100Z",
      "substation_id": "24",
      "decision_status": "needs_review",
      "decision_summary": "입력 정보가 부족하여 수동 검토가 필요합니다.",
      "recommended_action": "운영자 검토 요청",
      "priority_score": null,
      "priority_rank": null,
      "reason_codes": [
        "insufficient_prediction_context"
      ],
      "operator_note": null,
      "metadata": {
        "rule_version": "team-owned-v1"
      },
      "created_at": "2026-06-23T00:00:00+00:00"
    }
  }
}
```

### 6.5 Agent A 고정 영역 / 팀원 구현 영역

#### Agent A가 고정하는 것

- 입력 shape
- 출력 shape
- `agent_decisions` DB 매핑
- `decision_status`의 최소 후보
  - `action_required`
  - `needs_review`
  - `insufficient_data`

#### Agent 팀원이 설계할 것

- rule 산식
- priority score 계산 방식
- reason code 생성 규칙
- fallback 분기 세부 정책

### 6.6 DB 매핑

- `decision` -> `agent_decisions`

## 7. State 최소 필드

LangGraph 팀이 바로 가져갈 수 있게, 최소 State 필드는 아래로 고정한다.

```json
{
  "raw_event": {},
  "normalized_feature": {},
  "prediction": {},
  "decision": {},
  "history_context": {},
  "fallback_flag": false,
  "log_refs": []
}
```

## 8. 전체 mock 흐름

1. PreDist row를 `ingest_normalize_tool`에 넣는다.
2. `raw_event`, `normalized_feature`를 만든다.
3. ML mock output을 `predict_adapter_tool`에 넣는다.
4. canonical prediction row를 만든다.
5. prediction과 history context를 `decision_tool`에 넣는다.
6. decision row를 만든다.

## 9. 한 줄 정리

이번 문서는 **Agent A가 팀원에게 넘겨줄 수 있는 최소 Tool I/O 계약 기준본**이다.  
이후 LangChain/LangGraph 팀은 이 shape 위에서 rule과 orchestration만 설계하면 된다.
