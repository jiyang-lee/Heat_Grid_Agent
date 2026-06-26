# 2026-06-26 Priority model comparison diary

## 목적

우선순위 산정에서 기존 rule-base와 팀원 LGBM priority 모델, 새로 설계한 LGBM priority head를 비교했다.

처음에는 upstream IF/risk/leadtime 출력과 window feature를 함께 넣으면 LGBM이 rule-base를 크게 이길 수 있는지 확인했다. 이후 성능이 비정상적으로 높게 나와 feature leakage와 split 오염 가능성을 감사했고, 운영 추론 기준으로 다시 실험했다.

## 확인한 모델 패키지

검토한 팀원 모델 자료:

```text
lgbm_priority_model/
priority_with_readme/
```

확인 결과 `lgbm_priority_model` 안에는 두 패키지가 있었다.

```text
heatgrid_priority_model_2026-06-26
heatgrid_prediction_priority_models_2026-06-26
```

둘의 priority LGBM joblib은 동일한 모델이었다. 두 번째 패키지는 anomaly/risk/leadtime upstream 모델까지 포함한 통합 패키지였다.

`priority_with_readme`의 팀원 학습 코드는 7개 feature를 사용한다.

```text
anomaly_score
risk_probability
risk_score
leadtime_prob_0-24h
leadtime_prob_1-3d
leadtime_prob_3-7d
predicted_lead_time_confidence
```

## 초기 expanded LGBM 실험

처음에는 rule-base가 없다고 가정하고, 아래 입력으로 priority regression을 다시 학습했다.

```text
IF anomaly output
risk model output
leadtime model output
trainable_windows.csv numeric/window feature
risk level one-hot
predicted leadtime bucket one-hot
```

명시적으로 제외한 항목:

```text
priority_score
priority_level
priority_reason
risk_base_score
risk_probability_component_score
leadtime_component_score
anomaly_component_score
history_adjustment_score
lead_time_bucket_distance
lead_time_target
predicted_lead_time_index
label / fault_event_id / estimated_lead_time_hours
```

초기 결과에서는 holdout 기준 expanded LGBM이 rule-base를 크게 이겼다.

하지만 이 결과는 그대로 신뢰할 수 없다고 판단했다.

## leakage 감사

성능이 너무 높아 feature importance와 source pipeline을 확인했다.

문제 원인:

```text
PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
```

오프라인 leadtime score 생성은 `label == pre_fault` 행만 대상으로 수행했다. 이후 priority engine은 risk score 전체에 leadtime score를 left join했다.

그 결과:

```text
normal row: predicted_lead_time_bucket / leadtime_prob_* 100% missing
pre_fault row: predicted_lead_time_bucket / leadtime_prob_* 0% missing
```

즉 `predicted_lead_time_bucket_missing`이 사실상 정답 힌트로 작동했다.

반면 실제 운영 추론 패키지에서는 모든 row에 leadtime을 예측한다.

```text
inference_handoff/heatgrid_inference_package_2026-06-26/src/heatgrid_inference/scoring.py
```

따라서 오프라인 `priority_engine_scores_tuned.csv` 기준의 초기 expanded LGBM 결과는 폐기했다.

## 운영 추론 기준 재실험

실제 raw inference output 기준으로 다시 평가했다.

입력:

```text
report/priority_model_comparison/raw_priority_lgbm_vs_rule_labeled_rows.csv
```

이 파일은 `raw_inference_scores.csv`에서 label join이 가능한 row만 평가용으로 뽑은 것이다.

중요 조건:

```text
leadtime missing count = 0
normal/pre_fault 모두 leadtime 예측값 존재
```

수정된 보고서:

```text
report/priority_model_comparison/expanded_lgbm_priority_no_rule_report.md
```

결론:

```text
expanded LGBM이 rule-base를 안정적으로 이겼다고 볼 수 없음
rule-base를 운영 baseline으로 유지
expanded LGBM은 추가 검증 후보
```

## split 의미 정리

이번 비교에서 사용한 split:

```text
split_time_based
split_substation_based
split_regime_based
```

해석:

```text
time holdout: 같은 설비의 미래 구간 일반화
substation holdout: 처음 보는 설비/기계실 일반화
regime holdout: 다른 제조사/설비 구성/계절/운전 조건 일반화
```

운영 관점에서 가장 중요하게 본 것은 `substation holdout`이다. 새 설비나 처음 보는 현장에서도 안정적으로 작동해야 하기 때문이다.

## 상황별 샘플링 실험

rule-base를 이길 수 있는지 보기 위해 상황별 train sampling/weighting 실험을 추가했다.

스크립트:

```text
report/priority_model_comparison/sampled_lgbm_priority_experiment.py
```

보고서:

```text
report/priority_model_comparison/sampled_lgbm_priority_report.md
```

실험 전략:

```text
baseline_no_weight
severity_weighted
hard_case_weighted
event_balanced
substation_balanced
combined_context_weighted
combined_context_resampled
```

원칙:

```text
train split에만 sampling/weight 적용
validation/holdout은 원분포 유지
모델과 threshold는 validation에서만 선택
holdout은 최종 평가에만 사용
```

핵심 결과:

| split | rule F1 | best LGBM F1 | best strategy | rule NDCG@R | best LGBM NDCG@R | verdict |
| --- | ---: | ---: | --- | ---: | ---: | --- |
| time holdout | 0.6290 | 0.6970 | hard_case_weighted | 0.7089 | 0.6962 | F1 개선, ranking 미달 |
| substation holdout | 0.7965 | 0.7748 | hard_case_weighted | 0.8050 | 0.7942 | rule-base 우세 |
| regime holdout | 0.7013 | 0.7634 | severity_weighted | 0.7797 | 0.7711 | F1 개선, ranking 미달 |

해석:

- `hard_case_weighted`는 가장 가능성이 있는 방향이다.
- time/regime holdout에서는 LGBM이 high/urgent F1을 개선했다.
- 그러나 ranking 지표인 `NDCG@R`은 rule-base가 더 안정적이다.
- substation holdout에서는 F1과 NDCG@R 모두 rule-base가 더 좋다.

최종 판정:

```text
상황별 sampling은 효과가 있다.
하지만 현재 기준에서는 LGBM이 rule-base를 완전히 대체할 수준은 아니다.
운영 baseline은 rule-base 유지, LGBM은 후보 모델로 보류한다.
```

## ranking 지표 해석

Priority 문제는 단순 회귀 정확도보다 점검 순서가 중요하다.

이번 실험에서 본 ranking 지표:

```text
precision@R
recall@R
NDCG@R
precision@100
recall@100
NDCG@100
```

특히 `NDCG@R`은 실제 pre_fault 개수만큼 Top R을 뽑았을 때, 더 급한 0-24h / 1-3d 케이스를 위쪽에 잘 배치했는지를 본다.

따라서 F1이 높아도 NDCG@R이 낮으면 운영 점검 순서 품질은 떨어질 수 있다.

## 산출물

주요 산출물:

```text
report/priority_model_comparison/priority_lgbm_vs_rule_report.md
report/priority_model_comparison/priority_lgbm_vs_rule_plotly.html
report/priority_model_comparison/priority_lgbm_rule_hybrid_report.ipynb
report/priority_model_comparison/priority_with_readme_audit.md
report/priority_model_comparison/raw_priority_lgbm_vs_rule_report.md
report/priority_model_comparison/expanded_lgbm_priority_no_rule_report.md
report/priority_model_comparison/sampled_lgbm_priority_report.md
```

커밋 제외 대상:

```text
report/priority_model_comparison/raw_inference_scores.csv
```

이 파일은 약 278MB이며 GitHub 일반 push 대상이 아니다. 재생성 가능한 raw inference 중간 산출물이므로 commit에서 제외한다.

## 다음 판단

현재 단계에서 발표/보고서에 쓸 수 있는 결론:

```text
rule-base는 단순 if문이 아니라 upstream ML output을 안정적으로 조합하는 decision layer다.
LGBM priority head는 sampling/weighting으로 일부 개선 가능성이 있지만, 새 설비 일반화와 ranking 품질에서 아직 rule-base를 넘지 못했다.
따라서 rule-base를 운영 baseline으로 유지하고, LGBM은 hard-negative weighting 또는 ranking objective 기반 후속 후보로 둔다.
```

