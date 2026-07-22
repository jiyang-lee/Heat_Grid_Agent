# M1 Specialist 보고서

이 보고서는 M1-only 범위에서 current-best priority와 M1 specialist priority를 병렬 비교한다.

## 범위

- manufacturer filter: `manufacturer 1`
- 이 저장소는 M1 row만 대상으로 fit/score/validation을 수행한다.
- 공식 M1 agent card의 `priority_score`, `priority_level`은 label-free Risk/pre-event gate v4다.
- 공식 정책 버전: `m1_risk_pre_event_priority_v4`
- 공식 조건: restored Risk score >= 0.78 또는 pre-event probability >= 0.99
- 원래 current-best priority는 `current_best_priority_score`, `current_best_priority_level`로 보존한다.
- 요청 v2 0.72/0.28은 `m1_hybrid_priority_score`, `m1_hybrid_priority_level`로 보존한다.
- 이전 v1 0.65/0.35는 `legacy_priority_score`, `legacy_priority_level`로 보존한다.
- `m1_specialist_*` 컬럼은 M1 specialist 병렬 근거로 보존한다.

## Threshold

- m1_specialist high 기준: 75.000
- m1_specialist urgent 기준: 90.000
- m1_hybrid high 기준: 67.500
- m1_hybrid urgent 기준: 82.500
- evidence medium 기준: 90.000
- evidence high 기준: 99.000
- evidence urgent 기준: 99.800
- v4 Risk high/urgent 기준: 0.780 / 0.920
- v4 pre-event high/urgent 기준: 0.990 / 0.998

## Holdout 지표
| policy | split | metric_scope | row_count | precision | recall | false_positive_rate | tp | fp | fn | tn | mean_score | fault_events | detected_fault_events | fault_event_recall | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_best_priority | holdout | row | 183.0 | 0.7704918032786885 | 0.6103896103896104 | 0.1320754716981132 | 47.0 | 14.0 | 30.0 | 92.0 | 43.77953387978142 |  |  |  |  |
| current_best_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 7.0 | 0.875 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |
| m1_specialist_priority | holdout | row | 183.0 | 0.5686274509803921 | 0.37662337662337664 | 0.20754716981132076 | 29.0 | 22.0 | 48.0 | 84.0 | 54.58153003442786 |  |  |  |  |
| m1_specialist_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 5.0 | 0.625 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |
| legacy_priority | holdout | row | 183.0 | 1.0 | 0.2727272727272727 | 0.0 | 21.0 | 0.0 | 56.0 | 106.0 | 47.56023253390767 |  |  |  |  |
| legacy_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 5.0 | 0.625 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |
| m1_hybrid_priority | holdout | row | 183.0 | 1.0 | 0.5324675324675324 | 0.0 | 41.0 | 0.0 | 36.0 | 106.0 | 46.80409280308243 |  |  |  |  |
| m1_hybrid_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 7.0 | 0.875 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |
| m1_evidence_priority | holdout | row | 183.0 | 0.7857142857142857 | 0.42857142857142855 | 0.08490566037735849 | 33.0 | 9.0 | 44.0 | 97.0 | 86.98528125091039 |  |  |  |  |
| m1_evidence_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 6.0 | 0.75 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |
| m1_risk_pre_event_priority | holdout | row | 183.0 | 0.835820895522388 | 0.7272727272727273 | 0.10377358490566038 | 56.0 | 11.0 | 21.0 | 95.0 | 84.61535907779408 |  |  |  |  |
| m1_risk_pre_event_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 7.0 | 0.875 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |