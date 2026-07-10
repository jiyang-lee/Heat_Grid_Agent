# 검증 및 Ablation

## 1. Row 정합성

각 단계의 key 보존 여부를 확인한다.

```text
canonical_windows -> priority_scores
canonical_windows -> agent_card
priority_scores -> merged_scores
priority_scores -> agent_card
agent_card -> canonical_windows
```

결과:

```text
output/reports/row_reconciliation.csv
output/reports/missing_agent_windows.csv
```

## 2. Threshold Sweep

다음 score에 대해 threshold별 precision, recall, false positive rate를 계산한다.

```text
anomaly_policy_score
anomaly_ensemble_score
risk_score
priority_score
```

결과:

```text
output/reports/threshold_sweep.csv
```

## 3. Active Policy Ablation

다음 후보를 비교한다.

```text
official_anomaly_evidence_event
risk_high_or_critical
m1_specialist_high_or_urgent
priority_high_or_urgent
anomaly_or_risk_high
```

결과:

```text
output/reports/ablation_summary.csv
output/reports/ablation_summary.md
```

## 4. Priority 민감도

risk, leadtime, anomaly context 가중치를 바꿨을 때 top10 overlap과 review_required 분포를 본다.

결과:

```text
output/reports/priority_weight_sensitivity.csv
```

## 5. Hard Normal Audit

label은 normal인데 risk 또는 anomaly가 높게 나온 case를 따로 뽑아 pseudo-clean false alarm 검토 대상으로 본다.

결과:

```text
output/reports/hard_normal_audit.csv
```

## 6. 지원 산출물 Metadata

저장소 인수인계용 supporting artifact도 metadata에 기록한다.

```text
output/reports/pipeline_run_metadata.json
artifacts/current_best/ARTIFACT_INDEX.csv
compare/m1_specialist_performance_comparison.ipynb
compare/m1_threshold_weight_rationale_report.ipynb
```

`pipeline_run_metadata.json`에는 active CSV, 모델 파일, `artifacts/current_best/`, `compare/` 파일의 크기와 SHA256이 포함된다.

추가 threshold/weight 근거:

```text
output/reports/anomaly_criticality_threshold_sweep.csv
output/reports/hybrid_weight_sweep.csv
output/reports/hybrid_weight_selection_summary.csv
output/reports/priority_engine_component_summary.csv
compare/m1_threshold_weight_rationale_report.ipynb
```
