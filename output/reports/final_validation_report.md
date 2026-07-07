# 최종 검증 보고서

## 현재 활성 계약
- 공식 agent `priority_score`와 `priority_level`은 M1 hybrid priority 산출물이다.
- 최종 agent card인 `output/agent_priority_card.csv`와 `output/agent/m1_agent_priority_card.csv`는 1226 rows / 55 columns다.
- `output/agent/m1_specialist_parallel_agent_card.csv`는 1252 rows / 29 columns의 M1 단독 병렬 근거 card이며, 최종 hybrid agent 계약이 아니다.
- M1 hybrid priority = 0.65 * current-best priority + 0.35 * M1 specialist priority.
- Hybrid 0.65/0.35는 모든 metric의 절대 최적값이 아니라 운영 선택점이다. 0.72/0.28 및 0.90/0.10 비교는 threshold/weight 근거 notebook에서 확인한다.
- Active anomaly policy는 IsolationForest ratio >= 0.90 AND Mahalanobis ratio >= 1.00이며, criticality 지속성을 함께 본다.
- 실제 M1 current-best risk level 기준은 medium=0.22, high=0.92, critical=0.92다. high와 critical cutoff가 같으므로 현재 M1 output에는 low/medium/critical row만 존재한다.
- 원래 current-best priority는 `current_best_priority_score`, `current_best_priority_level`로 보존한다.
- `m1_specialist_*` 필드는 active 근거 필드이며 risk/leadtime의 단독 대체 모델이 아니다.
- `m1_specialist_group_weight`는 현재 fault-label-derived group과 강하게 연결되어 있어 live inference 적용 시 별도 검토가 필요하다.
- M1 gate threshold는 독립 알람 최적값이 아니라 근거 threshold다. task/activity gate는 native label이 없어 독립 성능 claim으로 쓰지 않는다.

## 출처 추적
- [current best] risk, leadtime, priority body
- [current best models] 추적성을 위해 risk_model_best.joblib, leadtime_model_best.joblib 포함
- [current best supporting artifacts] metric, threshold, feature contract, score source, experiment trace는 artifacts/current_best 아래 보존
- [comparison notebooks] 성능 비교와 threshold/weight 근거 notebook은 compare 아래 보존
- [M1 anomaly] IsolationForest ratio >= 0.90 AND Mahalanobis ratio >= 1.00 active policy
- [M1 specialist] fault/task/activity/pre-event gate, fault group, review flag
- [agent card contract] output/agent 아래 컬럼 사전, value mapping, 컬럼 분류표 포함
- [report defense audit] docs/08_MODEL_REPORT_DEFENSE_AUDIT.md에 보고 방어 체크리스트와 재실험/문서 보완 구분 포함

## 실행 Metadata
- generated_at_utc: 2026-07-07T13:27:25.141492+00:00
- source_best_root: ../HeatGrid_Agent/best
- metadata_file: output/reports/pipeline_run_metadata.json
- supporting_artifact_count: 119
- compare_file_count: 5

## Row 정합성
| source_stage | target_stage | source_rows | target_rows | source_duplicate_keys | target_duplicate_keys | missing_from_target | missing_pre_fault | missing_normal | missing_label_distribution | missing_split_distribution |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| canonical_windows | priority_scores | 1252 | 1226 | 0 | 0 | 26 | 26 | 0 | pre_fault=26 | train=23; validation=3 |
| canonical_windows | agent_card | 1252 | 1226 | 0 | 0 | 26 | 26 | 0 | pre_fault=26 | train=23; validation=3 |
| priority_scores | merged_scores | 1226 | 1226 | 0 | 0 | 0 | 0 | 0 |  |  |
| priority_scores | agent_card | 1226 | 1226 | 0 | 0 | 0 | 0 | 0 |  |  |
| agent_card | canonical_windows | 1226 | 1252 | 0 | 0 | 0 | 0 | 0 |  |  |

## Threshold Sweep 예시
| threshold | tp | fp | fn | tn | precision | recall | f1 | false_positive_rate | score_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.1 | 295 | 926 | 0 | 5 | 0.2416052416052416 | 1.0 | 0.3891820580474934 | 0.9946294307196564 | anomaly_policy_score |
| 0.2 | 295 | 685 | 0 | 246 | 0.3010204081632653 | 1.0 | 0.4627450980392157 | 0.7357679914070892 | anomaly_policy_score |
| 0.3 | 270 | 479 | 25 | 452 | 0.3604806408544726 | 0.9152542372881356 | 0.5172413793103448 | 0.514500537056928 | anomaly_policy_score |
| 0.4 | 226 | 346 | 69 | 585 | 0.3951048951048951 | 0.7661016949152543 | 0.5213379469434832 | 0.3716433941997852 | anomaly_policy_score |
| 0.5 | 176 | 226 | 119 | 705 | 0.4378109452736318 | 0.5966101694915255 | 0.5050215208034433 | 0.2427497314715359 | anomaly_policy_score |
| 0.6 | 151 | 174 | 144 | 757 | 0.4646153846153846 | 0.511864406779661 | 0.4870967741935484 | 0.1868958109559613 | anomaly_policy_score |
| 0.7000000000000001 | 133 | 146 | 162 | 785 | 0.4767025089605735 | 0.4508474576271186 | 0.4634146341463415 | 0.1568206229860365 | anomaly_policy_score |
| 0.8 | 126 | 121 | 169 | 810 | 0.5101214574898786 | 0.4271186440677966 | 0.4649446494464944 | 0.1299677765843179 | anomaly_policy_score |
| 0.9 | 115 | 105 | 180 | 826 | 0.5227272727272727 | 0.3898305084745763 | 0.4466019417475728 | 0.112781954887218 | anomaly_policy_score |
| 0.1 | 295 | 931 | 0 | 0 | 0.2406199021207178 | 1.0 | 0.3879026955950033 | 1.0 | anomaly_ensemble_score |
| 0.2 | 295 | 931 | 0 | 0 | 0.2406199021207178 | 1.0 | 0.3879026955950033 | 1.0 | anomaly_ensemble_score |
| 0.3 | 295 | 931 | 0 | 0 | 0.2406199021207178 | 1.0 | 0.3879026955950033 | 1.0 | anomaly_ensemble_score |

## Active Policy Ablation
| variant | tp | fp | fn | tn | precision | recall | false_positive_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| official_anomaly_evidence_event | 30 | 43 | 265 | 888 | 0.410958904109589 | 0.1016949152542373 | 0.0461868958109559 |
| risk_high_or_critical | 220 | 12 | 75 | 919 | 0.9482758620689656 | 0.7457627118644068 | 0.0128893662728249 |
| m1_specialist_high_or_urgent | 97 | 124 | 198 | 807 | 0.4389140271493212 | 0.3288135593220339 | 0.1331901181525241 |
| priority_high_or_urgent | 211 | 13 | 84 | 918 | 0.9419642857142856 | 0.7152542372881356 | 0.0139634801288936 |
| anomaly_or_risk_high | 224 | 55 | 71 | 876 | 0.8028673835125448 | 0.7593220338983051 | 0.0590762620837808 |

## Priority 민감도
| scenario | w_risk | w_leadtime | w_context | top10_overlap_rate | review_required_in_top10 | mean_top10_score |
| --- | --- | --- | --- | --- | --- | --- |
| baseline_best | 0.55 | 0.3 | 0.15 | 0.2 | 8 | 96.03203432341056 |
| risk_heavy | 0.7 | 0.2 | 0.1 | 0.2 | 8 | 97.35468954894034 |
| leadtime_heavy | 0.45 | 0.4 | 0.15 | 0.2 | 8 | 95.95937909788071 |
| balanced | 0.5 | 0.3 | 0.2 | 0.2 | 8 | 94.78203432341054 |

## Hard Normal Review 건수

55