# Agent Card Value Mapping

## Priority

- `priority_score`: 최종 M1 restored Risk/pre-event gate v4 우선순위 점수다.
- `priority_level`: `urgent`, `high`, `medium`, `low` 중 하나다.
- `priority_source`: priority 생성 공식을 나타낸다.

## Risk

- `risk_level_calibrated`: `critical`, `high`, `medium`, `low` 중 하나다.
- `risk_score`: 높을수록 고장/정비 이벤트 전 위험이 크다고 본다.

## Leadtime

- `predicted_lead_time_bucket`: `0-24h`, `1-3d`, `3-7d` 중 하나다.
- 이 값은 고장 시각 단정이 아니라 우선순위 참고 신호다.

## Anomaly

- `anomaly_policy_score`: IF ratio 0.90과 Mahalanobis ratio 1.00을 모두 넘는지 보는 active 이상 점수다.
- `anomaly_event_label`: active policy criticality 기준 event 여부다.
- `anomaly_evidence_source`: 어떤 active anomaly 근거가 쓰였는지 설명한다.

## Specialist

- `m1_specialist_*`: M1 전용 gate 기반 보조 근거다.
- specialist 값은 risk/leadtime을 대체하지 않고 최종 priority 설명에 보태는 신호다.

## Review

- `review_required == True`: 근거 충돌 또는 애매한 신호가 있어 사람이 확인해야 한다.
- `review_reasons`: review가 필요한 이유 목록이다.