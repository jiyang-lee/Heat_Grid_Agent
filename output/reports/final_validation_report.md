# 최종 검증 보고서

## 현재 활성 계약
- 공식 agent `priority_score`와 `priority_level`은 M1 hybrid priority 산출물이다.
- Final agent cards `output/agent_priority_card.csv` and `output/agent/m1_agent_priority_card.csv` have 1252 rows / 55 columns.
- `output/agent/m1_specialist_parallel_agent_card.csv` has 1252 rows / 29 columns and is M1-only evidence, not the final hybrid ordering contract.
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
- generated_at_utc: 2026-07-08T00:49:12.987514+00:00
- source_best_root: ../HeatGrid_Agent/best
- metadata_file: output/reports/pipeline_run_metadata.json
- supporting_artifact_count: 119
- compare_file_count: 5

## Row 정합성
| source_stage | target_stage | source_rows | target_rows | source_duplicate_keys | target_duplicate_keys | missing_from_target | missing_pre_fault | missing_normal | missing_label_distribution | missing_split_distribution |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| canonical_windows | priority_scores | 1252 | 1252 | 0 | 0 | 0 | 0 | 0 |  |  |
| canonical_windows | agent_card | 1252 | 1252 | 0 | 0 | 0 | 0 | 0 |  |  |
| priority_scores | merged_scores | 1252 | 1252 | 0 | 0 | 0 | 0 | 0 |  |  |
| priority_scores | agent_card | 1252 | 1252 | 0 | 0 | 0 | 0 | 0 |  |  |
| agent_card | canonical_windows | 1252 | 1252 | 0 | 0 | 0 | 0 | 0 |  |  |

## Threshold Sweep 예시
| threshold | tp | fp | fn | tn | precision | recall | f1 | false_positive_rate | score_name |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.1 | 321 | 926 | 0 | 5 | 0.257417802727 | 1.0 | 0.40943877551 | 0.99462943072 | anomaly_policy_score |
| 0.2 | 321 | 685 | 0 | 246 | 0.319085487078 | 1.0 | 0.483798040693 | 0.735767991407 | anomaly_policy_score |
| 0.3 | 294 | 479 | 27 | 452 | 0.380336351876 | 0.915887850467 | 0.53747714808 | 0.514500537057 | anomaly_policy_score |
| 0.4 | 249 | 346 | 72 | 585 | 0.418487394958 | 0.775700934579 | 0.543668122271 | 0.3716433942 | anomaly_policy_score |
| 0.5 | 192 | 226 | 129 | 705 | 0.459330143541 | 0.598130841121 | 0.519621109608 | 0.242749731472 | anomaly_policy_score |
| 0.6 | 163 | 174 | 158 | 757 | 0.483679525223 | 0.507788161994 | 0.495440729483 | 0.186895810956 | anomaly_policy_score |
| 0.7 | 145 | 146 | 176 | 785 | 0.498281786942 | 0.451713395639 | 0.47385620915 | 0.156820622986 | anomaly_policy_score |
| 0.8 | 137 | 121 | 184 | 810 | 0.531007751938 | 0.426791277259 | 0.47322970639 | 0.129967776584 | anomaly_policy_score |
| 0.9 | 125 | 105 | 196 | 826 | 0.54347826087 | 0.389408099688 | 0.453720508167 | 0.112781954887 | anomaly_policy_score |
| 0.1 | 321 | 931 | 0 | 0 | 0.256389776358 | 1.0 | 0.408137317228 | 1.0 | anomaly_ensemble_score |
| 0.2 | 321 | 931 | 0 | 0 | 0.256389776358 | 1.0 | 0.408137317228 | 1.0 | anomaly_ensemble_score |
| 0.3 | 321 | 931 | 0 | 0 | 0.256389776358 | 1.0 | 0.408137317228 | 1.0 | anomaly_ensemble_score |

## Active Policy Ablation
| variant | tp | fp | fn | tn | precision | recall | false_positive_rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| official_anomaly_evidence_event | 30 | 43 | 291 | 888 | 0.41095890411 | 0.0934579439252 | 0.046186895811 |
| risk_high_or_critical | 266 | 120 | 55 | 811 | 0.689119170984 | 0.828660436137 | 0.128893662728 |
| m1_specialist_high_or_urgent | 116 | 129 | 205 | 802 | 0.473469387755 | 0.361370716511 | 0.138560687433 |
| priority_high_or_urgent | 105 | 42 | 216 | 889 | 0.714285714286 | 0.327102803738 | 0.0451127819549 |
| anomaly_or_risk_high | 270 | 125 | 51 | 806 | 0.683544303797 | 0.841121495327 | 0.134264232009 |

## Priority 민감도
| scenario | w_risk | w_leadtime | w_context | top10_overlap_rate | review_required_in_top10 | mean_top10_score |
| --- | --- | --- | --- | --- | --- | --- |
| baseline_best | 0.55 | 0.3 | 0.15 | 0.4 | 8 | 95.393233878 |
| risk_heavy | 0.7 | 0.2 | 0.1 | 0.4 | 8 | 96.9288225853 |
| leadtime_heavy | 0.45 | 0.4 | 0.15 | 0.5 | 8 | 95.3299263398 |
| balanced | 0.5 | 0.3 | 0.2 | 0.4 | 8 | 94.096748773 |

## Hard Normal Review 건수

125