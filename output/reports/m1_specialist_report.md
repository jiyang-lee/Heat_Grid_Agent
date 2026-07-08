# M1 Specialist 보고서

이 보고서는 M1-only 범위에서 current-best priority와 M1 specialist priority를 병렬 비교한다.

## 범위

- manufacturer filter: `manufacturer 1`
- 이 저장소는 M1 row만 대상으로 fit/score/validation을 수행한다.
- 공식 M1 agent card의 `priority_score`, `priority_level`은 M1 hybrid priority다.
- 원래 current-best priority는 `current_best_priority_score`, `current_best_priority_level`로 보존한다.
- `m1_specialist_*` 컬럼은 M1 specialist 병렬 근거로 보존한다.

## Threshold

- m1_specialist high 기준: 75.000
- m1_specialist urgent 기준: 90.000
- m1_hybrid high 기준: 82.500
- m1_hybrid urgent 기준: 95.000

## Holdout 지표
| policy | split | metric_scope | row_count | precision | recall | false_positive_rate | tp | fp | fn | tn | mean_score | fault_events | detected_fault_events | fault_event_recall | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_best_priority | holdout | row | 183.0 | 0.423841059602649 | 0.8311688311688312 | 0.8207547169811321 | 64.0 | 87.0 | 13.0 | 19.0 | 75.76836612021859 |  |  |  |  |
| current_best_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 8.0 | 1.0 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |
| m1_specialist_priority | holdout | row | 183.0 | 0.6730769230769231 | 0.45454545454545453 | 0.16037735849056603 | 35.0 | 17.0 | 42.0 | 89.0 | 56.269451187267975 |  |  |  |  |
| m1_specialist_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 7.0 | 0.875 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |
| m1_hybrid_priority | holdout | row | 183.0 | 0.6341463414634146 | 0.33766233766233766 | 0.14150943396226415 | 26.0 | 15.0 | 51.0 | 91.0 | 68.94374589368587 |  |  |  |  |
| m1_hybrid_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 4.0 | 0.5 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |