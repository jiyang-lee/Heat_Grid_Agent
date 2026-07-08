# 최종 결과

## 최종 사용 산출물

```text
output/agent_priority_card.csv
output/agent/m1_agent_priority_card.csv
output/m1_specialist_gate_scores.csv
output/m1_specialist_scores.csv
output/reports/final_validation_report.md
output/reports/m1_specialist_report.md
output/reports/m1_specialist_vs_current_best_comparison.csv
compare/m1_specialist_performance_comparison.ipynb
compare/m1_threshold_weight_rationale_report.ipynb
artifacts/current_best/ARTIFACT_INDEX.csv
```

## 최종 priority

최종 `priority_score`는 M1 hybrid priority다.

```text
priority_score
= 0.65 * current_best_priority_score
+ 0.35 * m1_specialist_priority_score
```

해석:

- current-best 모델이 만든 risk/leadtime/priority 판단을 기본으로 둔다.
- M1 specialist gate가 fault/task/activity/pre-event 관점에서 보조 근거를 제공한다.
- 두 계열이 모두 높으면 점검 우선순위를 강하게 올린다.
- 두 계열이 불일치하면 `review_required`와 `review_reasons`로 사람이 확인할 사유를 남긴다.

## Anomaly 기준

```text
IF score ratio >= 0.90
AND Mahalanobis score ratio >= 1.00
criticality threshold = 5
```

`anomaly_policy_score`는 이 active policy의 기준 점수다. `anomaly_event_label`은 active anomaly가 지속된 경우에만 1이다.

## 결과 파일별 의미

`output/anomaly_scores.csv`:

- M1 정상 train 분포 대비 벗어난 정도를 score ratio로 저장한다.
- `anomaly_policy_score`, `anomaly_criticality`, `anomaly_event_label`이 포함된다.

`output/risk_scores.csv`:

- current-best risk 결과를 M1 범위로 필터링한 파일이다.

`output/leadtime_scores.csv`:

- leadtime bucket과 urgency score를 담는다.
- leadtime은 우선순위 참고 신호다.

`output/priority_scores.csv`:

- current-best priority 결과를 M1 범위로 필터링한 파일이다.

`compare/m1_specialist_performance_comparison.ipynb`:

- 최종본 도출 과정, 후보군 비교, 신뢰도, 고려사항을 발표/보고용으로 정리한 notebook이다.

`compare/m1_threshold_weight_rationale_report.ipynb`:

- anomaly/risk/leadtime/priority/hybrid threshold와 weight 설정 근거를 Plotly 차트로 설명한 notebook이다.
- risk가 priority engine에서 가장 큰 축으로 들어간 이유와 hybrid 0.65/0.35 근거를 별도 sweep으로 확인한다.
- 0.65/0.35는 절대 metric-best가 아니라 운영 선택점이다. Holdout 기준 metric-best 후보는 `hybrid_weight_selection_summary.csv`에서 확인한다.

`artifacts/current_best/`:

- current-best 원본 score, metric, threshold, audit, contract, experiment trace를 보존한 근거 폴더다.

`output/agent_priority_card.csv`:

- 최종 agent 입력 계약이다.
- priority, anomaly, risk, leadtime, M1 specialist, review/action 설명 컬럼을 포함한다.

## 현재 검증 요약

`output/anomaly_metrics.csv` 기준 holdout:

```text
policy_and_point:
precision 0.826
recall    0.494
FPR       0.075

policy_and_criticality:
precision 1.000
recall    0.273
FPR       0.000
```

`output/reports/ablation_summary.csv` 기준 active agent contract:

```text
risk_high_or_critical:
precision 0.948
recall    0.746
FPR       0.013

priority_high_or_urgent:
precision 0.942
recall    0.715
FPR       0.014
```

## 권장 해석

이 결과는 제어실/설비 담당자가 먼저 봐야 하는 대상을 정렬하는 용도다. 고장 시각을 단정하거나 자동 정비 지시를 내리는 용도가 아니다.
