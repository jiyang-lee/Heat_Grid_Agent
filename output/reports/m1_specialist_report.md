# M1 Specialist 보고서

이 보고서는 M1-only 범위에서 current-best priority와 M1 specialist priority를 병렬 비교한다.

## 범위

- manufacturer filter: `manufacturer 1`
- 이 저장소는 M1 row만 대상으로 fit/score/validation을 수행한다.
- 공식 M1 agent card의 `priority_score`, `priority_level`은 M1 hybrid priority다.
- 원래 current-best priority는 `current_best_priority_score`, `current_best_priority_level`로 보존한다.
- `m1_specialist_*` 컬럼은 M1 specialist 병렬 근거로 보존한다.

## Threshold

- m1_specialist high 기준: 77.500
- m1_specialist urgent 기준: 92.500
- m1_hybrid high 기준: 67.500
- m1_hybrid urgent 기준: 82.500

## Holdout 지표
| policy | split | metric_scope | row_count | precision | recall | false_positive_rate | tp | fp | fn | tn | mean_score | fault_events | detected_fault_events | fault_event_recall | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current_best_priority | holdout | row | 183.0 | 0.725 | 0.7532467532467533 | 0.20754716981132076 | 58.0 | 22.0 | 19.0 | 84.0 | 55.04589398907104 |  |  |  |  |
| current_best_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 7.0 | 0.875 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |
| m1_specialist_priority | holdout | row | 183.0 | 0.64 | 0.4155844155844156 | 0.16981132075471697 | 32.0 | 18.0 | 45.0 | 88.0 | 58.053192074677604 |  |  |  |  |
| m1_specialist_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 7.0 | 0.875 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |
| m1_hybrid_priority | holdout | row | 183.0 | 0.896551724137931 | 0.6753246753246753 | 0.05660377358490566 | 52.0 | 6.0 | 25.0 | 100.0 | 56.09844831903334 |  |  |  |  |
| m1_hybrid_priority | holdout | fault_event |  |  |  |  |  |  |  |  |  | 8.0 | 7.0 | 0.875 | normal-event 기준 FPR은 별도 event contract가 없어 row false_positive_rate를 비교 기준으로 사용한다. |