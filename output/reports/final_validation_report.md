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
| 0.1 | 295 | 926 | 0 | 5 | 0.241605241605 | 1.0 | 0.389182058047 | 0.99462943072 | anomaly_policy_score |
| 0.2 | 295 | 685 | 0 | 246 | 0.301020408163 | 1.0 | 0.462745098039 | 0.735767991407 | anomaly_policy_score |
| 0.3 | 270 | 479 | 25 | 452 | 0.360480640854 | 0.915254237288 | 0.51724137931 | 0.514500537057 | anomaly_policy_score |
| 0.4 | 226 | 346 | 69 | 585 | 0.395104895105 | 0.766101694915 | 0.521337946943 | 0.3716433942 | anomaly_policy_score |
| 0.5 | 176 | 226 | 119 | 705 | 0.437810945274 | 0.596610169492 | 0.505021520803 | 0.242749731472 | anomaly_policy_score |
| 0.6 | 151 | 174 | 144 | 757 | 0.464615384615 | 0.51186440678 | 0.487096774194 | 0.186895810956 | anomaly_policy_score |
| 0.7 | 133 | 146 | 162 | 785 | 0.476702508961 | 0.450847457627 | 0.463414634146 | 0.156820622986 | anomaly_policy_score |
| 0.8 | 126 | 121 | 169 | 810 | 0.51012145749 | 0.427118644068 | 0.464944649446 | 0.129967776584 | anomaly_policy_score |
| 0.9 | 115 | 105 | 180 | 826 | 0.522727272727 | 0.389830508475 | 0.446601941748 | 0.112781954887 | anomaly_policy_score |
| 0.1 | 295 | 931 | 0 | 0 | 0.240619902121 | 1.0 | 0.387902695595 | 1.0 | anomaly_ensemble_score |
| 0.2 | 295 | 931 | 0 | 0 | 0.240619902121 | 1.0 | 0.387902695595 | 1.0 | anomaly_ensemble_score |
| 0.3 | 295 | 931 | 0 | 0 | 0.240619902121 | 1.0 | 0.387902695595 | 1.0 | anomaly_ensemble_score |

## Active Policy Ablation
| variant | tp | fp | fn | tn | precision | recall | false_positive_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| official_anomaly_evidence_event | 30 | 43 | 265 | 888 | 0.41095890411 | 0.101694915254 | 0.046186895811 |
| risk_high_or_critical | 220 | 12 | 75 | 919 | 0.948275862069 | 0.745762711864 | 0.0128893662728 |
| m1_specialist_high_or_urgent | 97 | 124 | 198 | 807 | 0.438914027149 | 0.328813559322 | 0.133190118153 |
| priority_high_or_urgent | 211 | 13 | 84 | 918 | 0.941964285714 | 0.715254237288 | 0.0139634801289 |
| anomaly_or_risk_high | 224 | 55 | 71 | 876 | 0.802867383513 | 0.759322033898 | 0.0590762620838 |

## Priority 민감도
| scenario | w_risk | w_leadtime | w_context | top10_overlap_rate | review_required_in_top10 | mean_top10_score |
| --- | --- | --- | --- | --- | --- | --- |
| baseline_best | 0.55 | 0.3 | 0.15 | 0.2 | 8 | 96.0320343234 |
| risk_heavy | 0.7 | 0.2 | 0.1 | 0.2 | 8 | 97.3546895489 |
| leadtime_heavy | 0.45 | 0.4 | 0.15 | 0.2 | 8 | 95.9593790979 |
| balanced | 0.5 | 0.3 | 0.2 | 0.2 | 8 | 94.7820343234 |

## Hard Normal Review 건수

55