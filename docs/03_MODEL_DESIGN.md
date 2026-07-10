# 모델 설계

## 1. Anomaly

입력:

- `trainable_windows.csv`
- baseline metadata에 기록된 feature columns
- train split 중 `label == normal`

절차:

```text
정상 train window 추출
-> StandardScaler
-> IsolationForest score
-> LedoitWolf covariance 기반 Mahalanobis distance
-> train normal q99 threshold
-> score ratio 계산
-> active anomaly policy 적용
-> criticality 누적
-> anomaly_event_label 생성
```

active anomaly policy:

```text
iforest_score_ratio >= 0.90
AND mahalanobis_score_ratio >= 1.00
```

`anomaly_policy_score`:

```text
min(iforest_score_ratio / 0.90, mahalanobis_score_ratio / 1.00)
```

의미:

정상으로 정의한 window 분포에서 얼마나 멀어졌는지를 보는 구조다. 고장 이력을 직접 맞히는 supervised fault classifier가 아니라 정상 대비 이탈 정도를 보는 anomaly detector다.

## 2. Risk

모델 파일:

```text
models/risk/risk_model_best.joblib
models/risk/risk_model_best_metadata.json
```

출력:

- `risk_probability`
- `risk_score`
- `risk_level_calibrated`

의미:

anomaly가 "정상과 얼마나 다른가"라면 risk는 "이 window가 신고/정비 전 위험 구간일 가능성이 얼마나 높은가"를 본다.

현재 M1 저장소의 기본 파이프라인에서는 `best` 산출 score CSV를 M1 범위로 bridge한다. 모델 파일은 current-best risk 근거와 향후 standalone inference 재현성을 위해 포함한다.

## 3. Leadtime

모델 파일:

```text
models/leadtime/leadtime_model_best.joblib
models/leadtime/leadtime_model_best_metadata.json
```

출력:

- `predicted_lead_time_bucket`
- `leadtime_urgency_score`

의미:

leadtime은 고장 시점을 단정하는 값이 아니다. 0-24h, 1-3d, 3-7d 중 어느 쪽에 가까운지 보는 참고 신호이며 priority 계산의 보조 신호로만 쓴다.

현재 M1 저장소의 기본 파이프라인에서는 `best` 산출 score CSV를 M1 범위로 bridge한다. 모델 파일은 current-best leadtime 근거와 향후 standalone inference 재현성을 위해 포함한다.

## 4. M1 Specialist

입력:

- 3rd_project_for_ML-main의 compact13 feature 설계
- M1 fault/task/activity RandomForest gate
- M1 pre-event LogisticRegression gate

출력:

- `m1_specialist_fault_probability`
- `m1_specialist_task_probability`
- `m1_specialist_activity_probability`
- `m1_specialist_pre_event_probability`
- `m1_specialist_priority_score`
- `m1_specialist_gate_review_required`
- `m1_specialist_gate_review_reasons`

의미:

M1 specialist는 current-best risk/leadtime을 대체하지 않는다. 대신 M1 전용 gate가 보는 pre-event/상태/고장군 근거를 priority에 35% 반영하고, agent 설명 근거로 제공한다.

## 5. Priority

metadata:

```text
models/priority/priority_engine_best_metadata.json
artifacts/current_best/model_metadata/priority_engine_best_metadata.json
```

출력:

- `priority_score`
- `priority_level`

현재 공식:

```text
priority_score
= 0.65 * current_best_priority_score
+ 0.35 * m1_specialist_priority_score
```

의미:

여러 substation 중 먼저 확인해야 할 대상을 정렬하기 위한 최종 점수다. current-best를 기본축으로 유지하면서 M1 specialist gate 근거를 보조 반영한다.

current-best priority score의 원본과 ranking 비교 산출물은 `artifacts/current_best/source_score_outputs/priority_scores.csv`, `artifacts/current_best/reports/priority/`, `artifacts/current_best/reports/operational/`에 보존한다.

## 6. Operational Router

생성 항목:

- review flag
- review reason
- trust level
- stable crossing
- shadow priority
- recommended action

이 계층은 예측을 대체하지 않고, 후속 agent가 "왜 이 설비를 먼저 봐야 하는지" 설명할 수 있게 만든다.
