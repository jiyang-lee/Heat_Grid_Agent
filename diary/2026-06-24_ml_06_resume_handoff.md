# 2026-06-24 ML 06 Resume Handoff

## 목적

이 문서는 Codex를 껐다 켠 뒤에도 현재 프로젝트 상태와 다음 작업 방향을 바로 이어갈 수 있도록 남기는 handoff 기록이다.

이 문서 하나만 읽어도 아래를 알 수 있어야 한다.

```text
1. 프로젝트 ML 방향
2. 지금까지 고정한 결정사항
3. 현재 남아 있는 핵심 문제
4. 다음 작업 우선순위
5. 마지막 사용자 질문과 답변
```

## 프로젝트 ML 방향

현재 HeatGrid Copilot 프로젝트의 메인 ML 체인은 다음 구조로 고정한다.

```text
PreDist operational_data
-> 전처리 / 윈도우화
-> Isolation Forest
-> anomaly_score
-> faults.csv 기준 위험구간 라벨 생성
-> LightGBM
-> risk_probability / risk_score
-> Priority Engine
-> Agent
```

해석 원칙:

- Isolation Forest는 이상징후 탐지용이다.
- LightGBM은 고장 확정 모델이 아니다.
- LightGBM은 `faults.csv`의 고장신고 전 위험 패턴과의 유사도를 보는 모델이다.
- 최종 출력은 Agent와 Priority Engine이 쓰는 위험 정보다.

## 현재 메인 구현 상태

현재 메인 06 기준 핵심 노트북/스크립트:

```text
PREPROCESSING/osj/03_preprocess_windows.ipynb
PREPROCESSING/osj/04_feature_selection.ipynb
PREPROCESSING/osj/05_baseline_anomaly_model.ipynb
PREPROCESSING/osj/06_risk_leadtime_model.ipynb
PREPROCESSING/osj/06_leadtime_bucket_model.ipynb
```

관련 문서:

```text
PREPROCESSING/docs/03_preprocess_windows.md
PREPROCESSING/docs/04_feature_selection.md
PREPROCESSING/docs/05_baseline_anomaly_model.md
PREPROCESSING/docs/06_risk_leadtime_model.md
PREPROCESSING/docs/06_leadtime_bucket_model.md
PREPROCESSING/docs/06_followup_tuning.md
PREPROCESSING/docs/06_feature_importance_audit.md
PREPROCESSING/docs/06_drift_feature_ablation.md
PREPROCESSING/docs/06_manufacturer2_sh_fp_audit.md
PREPROCESSING/docs/06_group_calibration.md
```

## 이미 반영된 주요 결정사항

### 1. risk threshold 고정

메인 06 산출물은 아래 threshold를 사용한다.

```text
medium >= 0.22
high >= 0.44
critical >= 0.90
```

관련 파일:

```text
data/processed/ml_risk/lgbm_risk_thresholds.csv
data/processed/ml_risk/models/risk_model_metadata.json
```

### 2. leadtime 기본 체인 3버킷 승격

기본 leadtime bucket은 이제 아래 3개다.

```text
0-24h
1-3d
3-7d
```

관련 파일:

```text
data/processed/ml_leadtime/leadtime_bucket_metrics.csv
data/processed/ml_leadtime/models/leadtime_bucket_model_metadata.json
```

### 3. group-aware calibration 추가

현재 오탐이 심한 그룹에 대해 운영용 threshold override를 추가했다.

기본:

```text
high >= 0.44
```

override:

```text
manufacturer 2 + SH:
  high >= 0.78
```

이 보정은 확률값 자체를 바꾸지 않고, `risk_level` 판정만 더 엄격하게 적용한다.

관련 파일:

```text
PREPROCESSING/osj/06_group_calibration.py
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
data/processed/ml_risk/lgbm_risk_metrics_calibrated.csv
data/processed/ml_risk/lgbm_group_threshold_overrides.csv
data/processed/ml_risk/models/risk_model_group_calibration.json
```

## 현재 성능 기준

### calibration 전 overall holdout

`split_event_regime_based` holdout:

```text
precision 0.5476
recall    0.5349
f1        0.5412
fpr       0.1776
```

### calibration 후 overall holdout

```text
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449
```

### calibration 후 manufacturer 2 / SH holdout

```text
precision 0.6000
recall    0.5000
f1        0.5455
fpr       0.0755
```

해석:

- calibration은 오탐을 줄이는 데 실제로 효과가 있었다.
- 대신 recall은 소폭 희생되었다.
- 현재는 운영 안정화 관점에서 수용 가능한 trade-off로 판단했다.

## 지금까지 한 분석에서 나온 핵심 판단

### 1. feature importance audit 결과

중요한 점:

- gain importance와 holdout permutation importance가 다르게 나왔다.
- train에서 세게 먹히는 feature가 holdout에서 반드시 좋은 건 아니었다.

특히 재검토 후보:

```text
day_of_year
days_since_last_any_event
p_net_supply_temperature__mean
p_net_supply_temperature__max
network_temperature_gap__mean
```

### 2. drift feature ablation 결과

위 feature들을 빼는 실험을 했지만,

- 일부는 precision/FPR은 좋아지고
- recall은 나빠지는 식으로 trade-off가 발생했다.

즉 현재 결과만으로는 전역 feature 삭제를 바로 메인에 반영할 수준은 아니다.

### 3. manufacturer 2 / SH false positive audit 결과

holdout 오탐이 이 그룹에 집중되어 있었고,
오탐을 밀어올린 feature는 주로 아래 조합이었다.

```text
days_since_last_any_event
days_since_last_task_event
p_net_return_temperature__max
network_temperature_gap__mean
p_net_supply_temperature__mean
p_net_supply_temperature__max
```

즉 현재 오탐은 단일 feature 하나보다는

```text
event-context + thermal-gap 계열의 결합
```

으로 보는 것이 맞다.

## 현재 남아 있는 핵심 문제

지금 단계는 끝난 상태가 아니다.

현재 상태는:

```text
운영 가능하도록 1차 안정화는 됨
근본 feature engineering은 아직 더 해야 함
```

아직 남은 개선 포인트:

### 1. event-context feature 재설계

현재 문제 feature:

```text
days_since_last_any_event
days_since_last_task_event
```

다음 개선 방향:

- raw days 그대로 쓰지 말고 bucket화
- clipping
- 최근 7일 / 30일 / 90일 중심 재표현

### 2. thermal feature 재표현

현재 문제 후보:

```text
network_temperature_gap__mean
p_net_supply_temperature__mean
p_net_supply_temperature__max
p_net_return_temperature__max
```

다음 개선 방향:

- 절대값보다 관계식화
- 외기온도 대비 정규화
- 같은 그룹 기준 z-score
- 직전 윈도우 대비 변화량

### 3. calibration 고도화

지금은 단순 rule-based override다.

더 정교한 다음 후보:

- substation 11 단위 보정
- season 기반 보정
- calibration curve
- isotonic / Platt scaling

### 4. 사례 기반 error audit 확대

현재는 false positive를 중심으로 봤다.
앞으로는 false negative 사례집도 같이 봐야 한다.

## 지금 당장 다음 작업 우선순위

재시작 후 바로 이어서 할 일은 아래 순서가 맞다.

```text
1. 07 Priority Engine이 calibrated risk output을 읽게 연결
2. 08 Agent도 risk_level_calibrated 기준으로 판단하도록 연결
3. 그 다음에 event-context feature bucket/clipping 실험
4. thermal feature 관계식/정규화 실험
```

즉 현재 시점에서는

```text
운영 연결(07/08)
```

을 먼저 하고,

```text
근본 feature engineering 2차
```

는 그 다음 라운드로 가는 것이 맞다.

## 매우 중요한 운영 기준

현재 downstream에서는 원본 `risk_level`보다 아래를 우선 사용해야 한다.

```text
risk_level_calibrated
```

그리고 참고 입력 파일도 아래를 우선 사용한다.

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
```

원본 확률은 그대로 유지하고,
운영판단만 calibrated risk level을 쓴다.

## 마지막 사용자 질문과 답변

### 마지막 질문

```text
야 진짜로 이게 끝이야 더 개선할 여지가 있을텐데
```

### 마지막 답변 요지

답변은 “아니오”였다.

설명 핵심:

- 지금 한 것은 `운영 안정화 1차`일 뿐이다.
- 아직 근본 feature 개선은 더 남아 있다.
- 가장 큰 다음 과제는:

```text
1. event-context feature 재표현
2. thermal feature 정규화/관계식화
3. calibration 고도화
4. false positive / false negative 사례집 확대
```

특히 가장 현실적인 다음 1스텝으로는

```text
days_since_last_any_event / task_event를
raw 숫자 대신 bucket 또는 clipping으로 바꿔
06 재학습 비교
```

가 제안되었다.

## Codex 재시작용 짧은 지시문

새 세션에서 바로 붙여 넣을 수 있는 짧은 작업 지시문:

```text
diary/2026-06-24_ml_06_resume_handoff.md를 먼저 읽고 이어서 작업하라.

현재 메인 ML 체인은 Isolation Forest + LightGBM이다.
06에서는 risk threshold 0.22 / 0.44 / 0.90을 고정했고,
leadtime 기본 체인은 3버킷(0-24h / 1-3d / 3-7d)으로 승격했다.

또한 manufacturer 2 / SH 그룹에 대해 high threshold 0.78의 group-aware calibration을 추가했다.
downstream에서는 lgbm_risk_scores_calibrated.csv와 risk_level_calibrated를 우선 사용해야 한다.

다음 우선순위는
1) 07 Priority Engine 연결
2) 08 Agent 연결
그 다음에 event-context feature bucket/clipping 실험이다.
```


## 2026-06-25 update

오늘 06 보강 후보를 메인 산출물로 승격 가능한지 다시 검토했다.

### 추가 실험

```text
PREPROCESSING/osj/06_combined_feature_experiment.py
PREPROCESSING/osj/06_promoted_risk_model.py
```

핵심 판단:

```text
overall winner:
  thermal_group_zscore_only

manufacturer 2 / SH winner:
  event_context_only
```

그래서 위 둘을 나눠 쓰는 하이브리드 승격안도 만들었다.

승격 후보 산출물:

```text
data/processed/ml_risk/lgbm_risk_scores_promoted.csv
data/processed/ml_risk/lgbm_risk_metrics_promoted.csv
data/processed/ml_risk/models/risk_model_promoted_metadata.json
```

### 최종 결론

승격 후보는 문제 그룹에서는 괜찮지만, overall holdout 기준으로 현재 공식 calibrated 체인보다 약하다.

비교:

```text
current official calibrated holdout overall
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449

promoted candidate holdout overall
precision 0.5541
recall    0.4767
f1        0.5125
fpr       0.1542
```

따라서 공식본은 교체하지 않는다.

### 지금 기준 공식 downstream 입력

계속 사용할 것:

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
risk_level_calibrated
```

교체하지 않을 것:

```text
data/processed/ml_risk/lgbm_risk_scores_promoted.csv
```

즉 promoted는 승격 검토 후보로만 남기고, 운영 기준은 여전히 calibrated 본이다.

## 2026-06-25 leadtime update

오늘 leadtime 개선 실험도 같이 수행했다.

실행 파일:

```text
PREPROCESSING/osj/06_leadtime_improvement_experiments.py
```

결과 요약:

```text
baseline 3bucket holdout
accuracy 0.6512
macro_f1 0.4329

best timeflow candidate holdout
accuracy 0.6512
macro_f1 0.4405

4bucket holdout
accuracy 0.5814
macro_f1 0.3432

binary 2bucket holdout
accuracy 0.6163
macro_f1 0.6120
```

판단:

```text
main leadtime chain:
  keep current 3bucket

next promotion candidate:
  3bucket + timeflow_lag_delta_roll3

auxiliary urgency chain candidate:
  0-24h vs 1-7d
```

추가로 recent task/event 기반 label refinement는 현재 holdout에서는 효과가 없었다.
이유는 holdout pre_fault 86개 중 recent 7d task/event 행이 0개이기 때문이다.

## 2026-06-25 leadtime promotion update

leadtime는 timeflow 보강 후보를 승격 검토했다.

실행 파일:

```text
PREPROCESSING/osj/06_promoted_leadtime_model.py
```

결과:

```text
baseline holdout
accuracy   0.6512
macro_f1   0.4329
weighted   0.6385

timeflow promoted holdout
accuracy   0.6512
macro_f1   0.4405
weighted   0.6432
```

판단:

```text
leadtime는 promoted 후보를 차기 공식 후보로 채택 가능
```

관련 문서:

```text
PREPROCESSING/docs/06_leadtime_promotion_decision.md
```

## 2026-06-25 06 next improvement plan

추가 계획 문서:

```text
PREPROCESSING/docs/06_next_improvement_plan.md
```

다음 06 개선 우선순위:

```text
1. risk false negative audit 강화
2. risk event-context 상태형 재표현
3. risk thermal relation/group feature 보강
4. leadtime timeflow 확장
5. leadtime 2버킷 urgency 보조체인
6. pseudo label 재설계
```

핵심 원칙:

```text
이제 06 개선은 파라미터 튜닝보다
feature 표현과 label 구조를 건드리는 쪽이 맞다.
```

## 2026-06-25 false negative deep audit

추가 audit:

```text
PREPROCESSING/osj/06_false_negative_deep_audit.py
PREPROCESSING/docs/06_false_negative_deep_audit.md
```

핵심 결과:

```text
1. FN은 특정 그룹에 몰린다
   - manufacturer 2 | SH with buffer tank : 19
   - manufacturer 2 | SH + DHW            : 8
   - manufacturer 1 | SH + DHW            : 7
   - manufacturer 2 | SH                  : 6

2. medium FN도 많다
   - medium 23
   - low    19

3. leadtime 기준으로 1-3d FN이 제일 많다
   - 1-3d  28
   - 6-24h 10
   - 0-6h   4

4. score band 기준으로 0.22~0.44 사이 medium FN이 21개
```

판단:

```text
다음 06 개선의 핵심은
1-3d 중간 pre_fault를 high 쪽으로 더 잘 끌어올리는 feature 표현이다.
```

## 2026-06-25 state + thermal combined result

추가 실험:

```text
PREPROCESSING/osj/06_state_thermal_combined_experiment.py
PREPROCESSING/docs/06_state_thermal_combined_experiment.md
```

핵심 결과:

```text
best combined overall calibrated candidate:
  state_plus_group_zscore

metrics:
  precision 0.4681
  recall    0.5116
  f1        0.4889
  fpr       0.2336
  fn        42
  fn_1_3d   24
```

판단:

```text
FN 감소 효과는 분명하지만
현재 공식 calibrated 본(f1 0.5466, fpr 0.1449)을 넘지는 못함.
따라서 risk 공식본은 계속 calibrated 유지.
```

## 2026-06-25 weighting experiment

추가 실험:

```text
PREPROCESSING/osj/06_risk_weighting_experiment.py
PREPROCESSING/docs/06_risk_weighting_experiment.md
```

핵심 결과:

```text
best weighting calibrated candidate:
  leadtime_1_3d_x2_plus_group_x1_5

metrics:
  precision 0.4400
  recall    0.5116
  f1        0.4731
  fpr       0.2617
  fn        42
  fn_1_3d   25
```

판단:

```text
weighting은 FN 감소에는 분명 효과가 있다.
하지만 FPR이 많이 올라가서 현재 공식 calibrated 본을 교체할 수준은 아니다.
```

## 2026-06-25 07 priority engine 진행상황

추가 파일:

```text
PREPROCESSING/osj/07_priority_engine.py
PREPROCESSING/osj/07_priority_engine_tuned.py
PREPROCESSING/docs/07_priority_engine.md
```

입력 소스:

```text
risk 공식본:
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv

leadtime 승격본:
data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv
```

baseline v1 결과:

```text
output:
data/processed/ml_priority/priority_engine_scores.csv

distribution:
low    1697
urgent  514
high     88
medium   63
```

판단:

```text
urgent 쏠림이 크고 high/medium 중간 계층이 너무 얇다.
운영 triage 용도로는 분포를 다시 눌러야 한다.
```

tuned v2 결과:

```text
output:
data/processed/ml_priority/priority_engine_scores_tuned.csv

distribution:
low    1732
urgent  316
high    222
medium   92
```

현재 판단:

```text
07은 tuned v2를 기준 출력으로 쓰는 것이 타당하다.
완벽한 균형은 아니지만 v1보다 urgent 포화가 줄고 high 구간이 살아났다.
```

다음 단계:

```text
08 Agent 계층에서 07 tuned priority score를 읽어서
우선 점검 문장, 근거, 추천 액션을 만든다.
```
