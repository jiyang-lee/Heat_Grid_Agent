# HeatGrid Agent 작업 과정 및 레거시 분류 보고서

작성 기준일: 2026-06-26  
작성 위치: 프로젝트 루트  
검토 범위: `README.md`, `PREPROCESSING/`, `model_handoff/`, `inference_handoff/`, `report/`, `diary/`, `priority_with_readme/`, `lgbm_priority_model/`의 주요 문서와 코드

## 1. 보고서 목적

이 문서는 지금까지의 HeatGrid Agent 프로젝트 작업 흐름을 처음부터 정리하고, 어떤 파일이 레거시 또는 실험 자료로 분류되었는지, 왜 그렇게 되었는지, 그리고 그 과정에서 어떤 시행착오가 있었는지를 한 번에 확인하기 위해 작성했다.

핵심 질문은 다음이다.

```text
1. 현재 공식으로 봐야 하는 파이프라인은 무엇인가?
2. 레거시로 내려간 파일은 무엇이고 왜 내려갔는가?
3. 실험 파일과 공식 파일은 어떻게 구분하는가?
4. LGBM priority 모델과 rule-base priority engine 비교 과정에서 무엇을 배웠는가?
5. 외부 프로젝트에 넘길 때 무엇을 넘겨야 하는가?
```

## 2. 현재 최종 결론

현재 프로젝트의 공식 ML 흐름은 아래 구조다.

```text
raw operational data
-> label/context alignment
-> 6-hour window preprocessing
-> feature engineering / imputation / categorical mapping
-> Isolation Forest anomaly score
-> LightGBM risk model + group calibration
-> LightGBM 3-bucket leadtime model
-> rule-based Priority Engine v2_threshold48
-> inference handoff
```

현재 공식 기준은 단순한 모델 파일 묶음이 아니라, 원천 데이터에서 추론 결과까지 이어지는 전체 처리 절차다.

따라서 외부 프로젝트에 실제로 붙일 때는 `model_handoff`만 넘기는 것으로 충분하지 않다. 운영 데이터가 들어왔을 때 학습 때와 같은 전처리, 윈도우 생성, 피처 엔지니어링, 결측 보정, 카테고리 매핑, 모델 추론, priority scoring이 필요하므로 현재는 아래 패키지가 더 적절하다.

```text
inference_handoff/heatgrid_inference_package_2026-06-26/
```

`model_handoff/heatgrid_ml_models_2026-06-25/`는 모델 파일 중심 전달용이고, 대상 시스템이 이미 동일한 피처 생성 로직을 가지고 있을 때만 충분하다.

## 3. 현재 공식 파이프라인

공식 실행 순서는 `PREPROCESSING/osj/README.md` 기준으로 아래와 같다.

```text
00_load_dataset.ipynb
01_raw_inspection.ipynb
02_label_alignment.ipynb
03_preprocess_windows.ipynb
04_feature_selection.ipynb
05_baseline_anomaly_model.ipynb
06_risk_leadtime_models.ipynb
07_priority_engine.ipynb
08_model_handoff.ipynb
```

각 단계의 의미는 다음과 같다.

| 단계 | 역할 | 현재 상태 |
|---|---|---|
| 00 | PreDist 데이터 로드 및 배치 확인 | 공식 |
| 01 | raw operational/context 데이터 구조 확인 | 공식 |
| 02 | fault, disturbance, normal event 정렬 | 공식 |
| 03 | 6시간 windowing 및 feature engineering 기반 생성 | 공식 |
| 04 | 모델 입력 feature 계약 고정 | 공식 |
| 05 | Isolation Forest 기반 anomaly score 생성 | 공식 |
| 06 | LightGBM risk calibration 및 leadtime 모델 생성 | 공식 |
| 07 | anomaly/risk/leadtime 기반 priority 산정 | 공식 |
| 08 | Agent/서비스 전달용 모델 패키지 검증 | 공식 |

공식 Python 실행 파일은 아래 세 개로 좁혀져 있다.

```text
PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py
```

이 폴더의 원칙은 명확하다.

```text
pipeline_scripts/ = 공식 산출물 생성 코드
experiments/      = 실험, 감사, ablation 코드
archive/          = 공식 흐름에서 제외된 구버전 진입점
legacy/           = 방향 전환 시도 또는 더 이상 메인 기준이 아닌 자료
```

## 4. 레거시 및 실험 분류 전체 지도

| 경로 | 분류 | 이유 |
|---|---|---|
| `PREPROCESSING/osj/*.ipynb` | 공식 노트북 | 사람이 순서대로 실행하는 현재 canonical flow |
| `PREPROCESSING/osj/pipeline_scripts/` | 공식 코드 | 06/07 공식 산출물 생성에 직접 사용 |
| `PREPROCESSING/legacy/` | 레거시 아카이브 | `Autoencoder + paper-aligned` 전환 시도 자료 보존 |
| `PREPROCESSING/osj/archive/` | 구버전 아카이브 | wrapper/basic 구현이 공식 스크립트와 tuned 엔진으로 대체됨 |
| `PREPROCESSING/osj/experiments/` | 실험/감사 코드 | 성능 개선, 원인 분석, ablation용이며 공식 산출물에 자동 포함하지 않음 |
| `PREPROCESSING/docs/06_test/` | 과거 실험 문서 | 06 실험/감사 자료를 공식 문서와 분리 |
| `report/experiment_comparison/` | 실험 증거 | 모델 후보 비교, threshold sweep, 튜닝 결과 기록 |
| `report/priority_model_comparison/` | priority 비교 보고 | rule-base vs LGBM 비교, 누수 감사, 샘플링 실험 기록 |
| `model_handoff/` | 모델 중심 handoff | 학습된 모델과 메타데이터 전달용. 레거시는 아님 |
| `inference_handoff/` | 운영 추론 handoff | 외부 프로젝트 연동용. 전처리부터 스코어링까지 포함 |
| `priority_with_readme/` | 팀원 LGBM 학습 코드 | 현재 공식 priority는 아니며 비교/재검토 대상 |
| `lgbm_priority_model/` | 팀원 LGBM 전달 패키지 | priority LGBM 후보 패키지. 현재 공식 baseline 아님 |

## 5. 레거시로 분류된 파일과 이유

### 5.1 `PREPROCESSING/legacy/`

이 폴더는 `Autoencoder + paper-aligned` 방향 전환을 시도했던 자료를 보존한다.

대표 파일:

```text
PREPROCESSING/legacy/osj/06_paper_aligned_review.ipynb
PREPROCESSING/legacy/osj/06_paper_aligned_data_selection.ipynb
PREPROCESSING/legacy/osj/06_paper_aligned_autoencoder.ipynb
PREPROCESSING/legacy/osj/06_paper_aligned_event_eval.ipynb
PREPROCESSING/legacy/osj/06_paper_aligned_feature_attribution.ipynb

PREPROCESSING/legacy/docs/06_model_direction_decision.md
PREPROCESSING/legacy/docs/06_paper_aligned_review.md
PREPROCESSING/legacy/docs/06_paper_aligned_data_selection.md
PREPROCESSING/legacy/docs/06_paper_aligned_autoencoder.md
PREPROCESSING/legacy/docs/06_paper_aligned_event_eval.md
PREPROCESSING/legacy/docs/06_paper_aligned_feature_attribution.md
PREPROCESSING/legacy/docs/06_paper_aligned_agent_contract.md
```

레거시 분류 이유:

```text
1. paper-aligned Autoencoder 방향은 좋은 검토 자료였지만 최종 공식 운영 체인으로 승격되지 않았다.
2. 현재 공식 기준은 Isolation Forest -> LightGBM risk -> LightGBM leadtime -> rule-based priority다.
3. paper-aligned 자료는 논문 정렬형 event-wise anomaly detection 근사 실험으로 의미가 있지만, 현재 handoff 패키지와 직접 연결되는 공식 실행 경로는 아니다.
4. 삭제하면 방향 전환의 근거와 실패/보류 이유가 사라지므로 보존한다.
```

여기서 중요한 점은 `legacy`가 실패작이라는 뜻은 아니라는 것이다. 이 폴더는 "검토했지만 현재 공식 배포 경로에는 포함하지 않는 자료"다.

paper-aligned 시도에서 확인한 핵심 한계와 의미는 다음이다.

```text
- faults.csv는 실제 고장 onset이 아니라 신고 시점이다.
- fixed pre_fault window 분류는 라벨 불확실성이 크다.
- 제조사/configuration/substation regime 차이가 크다.
- 정상 행동 기반 anomaly detection과 event-wise 평가가 이론적으로는 더 맞을 수 있다.
- 다만 현재 프로젝트의 공식 산출물, handoff, 실험 비교 기준은 기존 06 체인을 보강하는 쪽으로 정리됐다.
```

### 5.2 `PREPROCESSING/osj/archive/`

이 폴더는 공식 실행 흐름에서 제외된 구버전 wrapper 또는 basic 구현을 보관한다.

대표 파일:

```text
PREPROCESSING/osj/archive/06_risk_official_wrapper.py
PREPROCESSING/osj/archive/06_leadtime_official_wrapper.py
PREPROCESSING/osj/archive/07_priority_engine_basic.py
```

분류 이유:

| 파일 | 내려간 이유 | 현재 대체 파일 |
|---|---|---|
| `06_risk_official_wrapper.py` | 과거 wrapper 진입점. 현재는 공식 calibration script를 직접 사용 | `pipeline_scripts/06_risk_calibration.py` |
| `06_leadtime_official_wrapper.py` | 과거 wrapper 진입점. 현재는 leadtime script를 직접 사용 | `pipeline_scripts/06_leadtime_model.py` |
| `07_priority_engine_basic.py` | priority v1 basic 구현. urgent 과포화와 중간 구간 분해력 부족 | `pipeline_scripts/07_priority_engine.py` |

특히 `07_priority_engine_basic.py`는 삭제가 아니라 보존 대상이다. v1에서 어떤 문제가 있었고, 왜 v2_threshold48로 바뀌었는지 비교 근거가 되기 때문이다.

### 5.3 `PREPROCESSING/osj/experiments/06_test/`

이 폴더는 엄밀히 말하면 레거시라기보다 실험/감사 보관소다.

대표 성격:

```text
false negative audit
feature importance audit
drift feature ablation
manufacturer 2 / SH false positive audit
risk weighting experiment
leadtime improvement experiment
hyperparameter tuning
thermal/event-context feature experiment
priority threshold sweep
priority LGBM regression candidate
```

분류 이유:

```text
1. 공식 산출물을 직접 생성하는 필수 실행 파일이 아니다.
2. 실험 결과가 좋더라도 즉시 공식에 반영하지 않고, 검증 후 pipeline_scripts로 승격해야 한다.
3. 일부 실험은 문제 그룹에서는 개선되지만 전체 holdout에서는 악화되었다.
4. 따라서 공식 코드와 섞지 않고 실험 증거로만 보관한다.
```

## 6. 시행착오 타임라인

### 6.1 초기 프로젝트 및 데이터 로드

초기에는 실행 환경, raw data 다운로드/정리, ML handoff/output contract 문서가 먼저 만들어졌다.

근거:

```text
diary/repository_migration_commit_history.md
PREPROCESSING/docs/00_load_dataset.md
PREPROCESSING/docs/ML_HANDOFF.md
PREPROCESSING/docs/ML_OUTPUT_CONTRACT.md
PREPROCESSING/docs/ML_PAPER_GUIDELINE.md
```

이 단계의 목적은 모델을 바로 만드는 것이 아니라, 이후 작업이 재현 가능하도록 데이터 위치, 실행 환경, 문서 기준을 잡는 것이었다.

### 6.2 00~05 전처리 및 Isolation Forest

이후 00~05 단계에서 raw inspection, label alignment, windowing, feature selection, Isolation Forest anomaly score 생성 흐름이 정리됐다.

현재 05의 역할은 고장 확정이 아니다.

```text
Isolation Forest = 정상 패턴과 다른 이상징후 점수 생성
anomaly_score = downstream risk/priority가 참고하는 연속 신호
```

주의해야 할 점:

```text
anomaly_label 자체를 고장이라고 해석하면 안 된다.
```

이 결론은 `PREPROCESSING/docs/PROJECT_ML_STATUS.md`와 05 관련 문서에서 반복된다.

### 6.3 06 risk/leadtime LightGBM 체인

06에서는 LightGBM 기반 risk 모델과 leadtime 모델을 구성했다.

현재 공식 risk 산출물:

```text
data/processed/ml_risk/lgbm_risk_scores_calibrated.csv
data/processed/ml_risk/lgbm_risk_metrics_calibrated.csv
data/processed/ml_risk/lgbm_group_threshold_overrides.csv
```

현재 공식 leadtime 산출물:

```text
data/processed/ml_leadtime/leadtime_bucket_scores_promoted.csv
data/processed/ml_leadtime/leadtime_bucket_metrics_promoted.csv
data/processed/ml_leadtime/leadtime_bucket_confusion_matrix_promoted.csv
```

06에서 겪은 핵심 문제는 다음이었다.

```text
1. faults.csv의 시점은 실제 고장 발생 시점이 아니라 신고 시점이다.
2. pre_fault label은 실제 고장 onset이 아니라 신고 전 구간 proxy다.
3. manufacturer/configuration/substation별 regime 차이가 커서 holdout 일반화가 흔들릴 수 있다.
4. manufacturer 2 / SH 정상 구간에서 false positive가 집중됐다.
5. 1-3d pre_fault 구간 false negative가 많이 남았다.
```

이 문제 때문에 한때 paper-aligned Autoencoder 방향을 검토했고, 동시에 기존 LightGBM 체인의 감사와 보정도 진행했다.

### 6.4 paper-aligned Autoencoder 방향 검토

paper-aligned 시도는 논문형 구조에 맞춰 아래 방향을 검토했다.

```text
normal event selection
-> normal behaviour model
-> reconstruction error
-> criticality counter
-> event-wise detection / false alarm / lead time
-> Agent contract mapping
```

이 접근은 고장 확정 classifier보다 현재 프로젝트 목적과 더 잘 맞는 면이 있었다.

장점:

```text
- normal behaviour 기준 이상징후 탐지
- point anomaly가 아니라 지속 이상 구간 평가
- event-wise false alarm / detection / lead time 평가 가능
- feature attribution으로 설명 가능성 확보
```

하지만 최종 공식 경로로 승격하지 않은 이유는 다음이다.

```text
1. 현재 main handoff와 운영 추론 패키지가 기존 05/06/07 체인 기준으로 정리됐다.
2. paper-aligned 구현은 근사 baseline 성격이 강하고, 모든 event에 대해 논문과 동일한 7일 test window를 완전히 보장하지 못했다.
3. 공식 산출물과 직접 연결되는 stable pipeline은 기존 06 체인을 보강한 쪽이었다.
4. 따라서 paper-aligned 자료는 삭제하지 않고 `PREPROCESSING/legacy/`에 보존했다.
```

### 6.5 06 risk 감사와 group calibration

risk 모델에서는 `manufacturer 2 / SH` holdout 정상 구간 false positive가 문제였다.

단순히 특정 feature를 전역 삭제하지 않은 이유:

```text
1. 오탐을 올리는 feature가 전체 holdout에서는 유효 신호이기도 했다.
2. 문제는 단일 feature가 아니라 event-context와 thermal-gap 계열의 결합이었다.
3. 전역 삭제는 다른 그룹의 recall을 해칠 수 있었다.
```

그래서 선택한 방식은 group-aware calibration이었다.

```text
risk_probability는 그대로 유지
manufacturer/configuration 조합에 따라 risk level threshold만 보정
```

공식 보정 결과:

```text
보정 전 holdout:
precision 0.5476
recall    0.5349
f1        0.5412
fpr       0.1776

보정 후 holdout:
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449
```

보정 후 recall은 조금 낮아졌지만 precision과 FPR이 개선되었고 전체 F1도 소폭 개선되어, 현재 공식 risk는 calibrated 본으로 유지됐다.

### 6.6 promoted risk 후보 보류

후속 실험에서는 아래 조합이 검토됐다.

```text
overall:
  thermal_group_zscore_only

manufacturer 2 / SH:
  event_context_only
```

문제 그룹 자체에서는 개선이 있었지만 전체 holdout에서는 현재 공식 calibrated 체인보다 나빠졌다.

```text
현재 공식 calibrated holdout:
precision 0.5867
recall    0.5116
f1        0.5466
fpr       0.1449
roc_auc   0.7628

승격 후보 hybrid holdout:
precision 0.5541
recall    0.4767
f1        0.5125
fpr       0.1542
roc_auc   0.7271
```

결론:

```text
promoted risk 후보는 공식으로 채택하지 않는다.
공식 risk는 calibrated 본을 유지한다.
```

### 6.7 leadtime promoted 후보 채택

leadtime에서는 `3버킷 유지 + timeflow_lag_delta_roll3 추가` 조합이 검토됐다.

기존 공식본 대비 promoted 후보:

```text
기존:
accuracy   0.6512
macro_f1   0.4329
weighted   0.6385
top2_acc   0.9651
bucket_mae 0.3837

promoted:
accuracy   0.6512
macro_f1   0.4405
weighted   0.6432
top2_acc   0.9651
bucket_mae 0.3837
```

큰 개선은 아니지만 나빠지지 않았고 macro F1과 weighted F1이 소폭 개선되어 현재 leadtime은 promoted 3-bucket 본을 공식으로 사용한다.

주의:

```text
leadtime은 실제 고장 발생 시점 예측이 아니다.
faults.csv 신고 시점 기준 pseudo leadtime bucket이다.
```

### 6.8 Priority Engine v1에서 v2_threshold48로 변경

초기 priority v1 basic은 아래 문제가 있었다.

```text
urgent 쏠림이 크고 high/medium 구간이 너무 얇았다.
운영 triage 계층으로 쓰기엔 중간 구간 분해력이 부족했다.
```

그래서 점수 스케일을 압축한 tuned v2가 만들어졌다.

현재 공식 priority engine:

```text
priority_engine_v2_threshold48
```

현재 점수 구조:

```text
priority_score
= risk_base_score
+ risk_probability_component_score
+ leadtime_component_score
+ anomaly_component_score
+ history_adjustment_score
```

현재 핵심 룰:

```text
risk level points:
critical -> 38
high     -> 28
medium   -> 15
low      -> 4

leadtime bucket points:
0-24h -> 18
1-3d  -> 10
3-7d  -> 4

risk probability component:
risk_probability * 18, 0~18 clamp

anomaly component:
anomaly_score * 6, 0~6 clamp

priority level:
score >= 70 -> urgent
score >= 48 -> high
score >= 34 -> medium
else        -> low
```

threshold 48 승격 이유:

```text
threshold 52:
TP 37 / FP 0 / Recall 0.4302 / F1 0.6016 / FPR 0.0000

threshold 48:
TP 44 / FP 0 / Recall 0.5116 / F1 0.6769 / FPR 0.0000
```

즉 threshold 48은 현재 holdout 기준에서 false positive를 늘리지 않으면서 recall과 F1을 높인 기준이다.

## 7. Priority Engine의 성격

현재 priority engine은 순수 ML 모델이 아니다.

정확한 표현은 다음이다.

```text
ML output을 입력으로 사용하는 rule-based decision layer
또는 ML-assisted rule-based priority engine
```

구조:

```text
raw data
-> preprocessing / feature engineering
-> ML models
   - anomaly_score
   - risk_probability
   - risk_level_calibrated
   - predicted_lead_time_bucket
   - leadtime confidence
-> rule-based priority engine
   - risk 점수
   - leadtime 점수
   - anomaly 점수
   - 이력 보정
   - threshold 적용
-> priority_score / priority_level / priority_reason
```

따라서 "룰베이스가 머신러닝으로 학습한다"는 표현은 부정확하다.

더 정확한 표현:

```text
앞단 머신러닝 모델들이 판단 재료를 만들고,
Priority Engine은 그 재료를 도메인 룰과 점수화 알고리즘으로 결합해
최종 우선순위를 산정한다.
```

이 구조의 장점:

```text
1. 설명 가능하다.
2. threshold와 점수 구성요소를 감사할 수 있다.
3. false positive를 운영적으로 제어하기 쉽다.
4. 작은 데이터와 라벨 불확실성 상황에서 안정적이다.
```

한계:

```text
1. 룰 점수 기준은 사람이 정한 구조라 데이터에서 자동 학습되지는 않는다.
2. 새로운 패턴을 스스로 재학습하지 못한다.
3. 더 강한 ML 모델이 충분한 검증에서 우세해지면 교체 또는 hybrid 전환 가능성이 있다.
```

## 8. 팀원 LGBM priority 모델 검토

### 8.1 검토한 패키지

팀원 priority 모델 관련 자료는 크게 두 위치에 있다.

```text
priority_with_readme/
lgbm_priority_model/
```

`lgbm_priority_model` 안에는 두 패키지가 있다.

```text
heatgrid_priority_model_2026-06-26
heatgrid_prediction_priority_models_2026-06-26
```

차이:

| 패키지 | 성격 |
|---|---|
| `heatgrid_priority_model_2026-06-26` | priority LGBM regression 단독 패키지 |
| `heatgrid_prediction_priority_models_2026-06-26` | anomaly/risk/leadtime upstream 모델 + priority LGBM 통합 패키지 |

확인 결과 두 패키지의 최종 priority LGBM joblib은 SHA256 기준 동일한 모델이었다.

즉 priority 결과 관점에서는 두 패키지가 서로 다른 모델 두 개를 의미하지 않는다. 하나는 priority만 포장한 것이고, 하나는 upstream 예측 체인까지 같이 포장한 것이다.

### 8.2 팀원 LGBM 구조

팀원 priority LGBM은 raw sensor를 직접 보는 모델이 아니다.

입력 feature는 upstream 모델 결과 7개다.

```text
anomaly_score
risk_probability
risk_score
leadtime_prob_0-24h
leadtime_prob_1-3d
leadtime_prob_3-7d
predicted_lead_time_confidence
```

target mapping:

```text
normal = 0
3-7d   = 33
1-3d   = 66
0-24h  = 100
```

split:

```text
substation_id % 3 == 0 -> holdout
```

중요한 제한:

```text
현재 repo에는 팀원 학습 기준 파일인
data/processed/ml_model_chain/model_chain_output.csv
가 없다.
```

따라서 팀원 metadata의 원래 학습/평가 결과는 현재 저장소에서 그대로 재현할 수 없다.

### 8.3 현재 공식 데이터 기준 1차 비교

현재 공식 `priority_engine_scores_tuned.csv` 기준으로 재스코어링했을 때, holdout에서는 rule-base가 더 안정적이었다.

대표 결과:

```text
holdout MAE:
Rule-based 20.5625
LGBM       26.1631

holdout high/urgent action:
Rule-based precision 0.8837 / recall 0.7103 / F1 0.7876
LGBM       precision 0.8333 / recall 0.3271 / F1 0.4698

holdout NDCG@R:
Rule-based 0.7805
LGBM       0.5976
```

결론:

```text
현재 공식 데이터 기준으로는 rule-base > 팀원 LGBM priority regression
```

### 8.4 raw inference 기준 재실험

사용자가 질문한 대로, 팀원 LGBM을 실제 raw data에서 출발한 inference 결과에 붙여 다시 비교했다.

흐름:

```text
data/raw_data/predist_v2
-> inference_handoff raw windowing
-> anomaly/risk/leadtime upstream score 생성
-> rule-based priority score
-> 팀원 LGBM priority head 적용
-> trainable_windows label과 key join 후 평가
```

중요 결과:

```text
raw inference 전체 rows: 331595
label join 가능 rows: 2526
label join rate: 0.7618%
```

raw inference 기준에서도 팀원 LGBM은 rule-base를 운영 공식 모델로 대체할 근거가 부족했다.

대표 holdout 결과:

```text
split_time_based holdout:
Rule F1 0.6290 / NDCG@R 0.7089
Team LGBM F1 0.3313 / NDCG@R 0.6270
```

해석:

```text
팀원 LGBM은 매우 보수적으로 높은 점수를 준다.
precision과 specificity는 좋아 보일 수 있지만 recall 손실이 크다.
운영 점검 우선순위에서는 놓치는 위험구간이 많아진다.
```

## 9. Expanded LGBM 실험과 누수 감사

### 9.1 초기 결과

사용자 요구에 따라 "룰베이스가 없었다고 가정하고", upstream output과 window feature를 넣은 expanded LGBM priority 모델을 실험했다.

초기 입력:

```text
IF anomaly output
risk model output
leadtime model output
trainable_windows numeric/window feature
risk level one-hot
predicted leadtime bucket one-hot
```

초기 결과는 LGBM이 rule-base를 크게 이기는 것처럼 보였다.

하지만 결과가 지나치게 좋아서 feature importance와 pipeline을 감사했다.

### 9.2 발견한 leakage

문제 원인:

```text
PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
```

오프라인 leadtime score 생성은 `label == pre_fault` 행만 대상으로 수행했고, 이후 priority engine은 risk score 전체에 leadtime score를 left join했다.

결과적으로:

```text
normal row:
predicted_lead_time_bucket / leadtime_prob_* 100% missing

pre_fault row:
predicted_lead_time_bucket / leadtime_prob_* 0% missing
```

즉 `predicted_lead_time_bucket_missing` 같은 missing indicator가 사실상 정답 힌트로 작동했다.

따라서 오프라인 `priority_engine_scores_tuned.csv` 기준 초기 expanded LGBM 결과는 폐기했다.

이것이 중요한 시행착오다.

```text
성능이 너무 좋으면 먼저 누수와 split 오염을 의심해야 한다.
```

### 9.3 raw inference 기준으로 다시 검증

실제 운영 추론 패키지에서는 모든 row에 leadtime을 예측한다.

근거 코드:

```text
inference_handoff/heatgrid_inference_package_2026-06-26/src/heatgrid_inference/scoring.py
```

따라서 raw inference 결과에서 label join 가능한 row만 뽑아 다시 실험했다.

재검증 데이터:

```text
report/priority_model_comparison/raw_priority_lgbm_vs_rule_labeled_rows.csv
rows: 2526
feature 수: 209
leadtime missing count: 0
```

누수 제거 후 holdout 결과:

```text
split_time_based:
Rule F1 0.6290 / NDCG@R 0.7089
Expanded LGBM F1 0.6966 / NDCG@R 0.6413

split_substation_based:
Rule F1 0.7965 / NDCG@R 0.8050
Expanded LGBM F1 0.6931 / NDCG@R 0.7764

split_regime_based:
Rule F1 0.7013 / NDCG@R 0.7797
Expanded LGBM F1 0.7353 / NDCG@R 0.7425
```

해석:

```text
time/regime에서는 LGBM이 F1을 일부 개선할 수 있다.
하지만 ranking 품질인 NDCG@R은 rule-base가 더 안정적이다.
substation holdout에서는 rule-base가 F1과 NDCG@R 모두 우세하다.
```

결론:

```text
누수 제거 후 expanded LGBM은 rule-base를 압도하지 않는다.
운영 baseline은 rule-base 유지가 맞다.
```

## 10. 상황별 샘플링 LGBM 실험

이후 상황별 train sampling/weighting을 적용해 LGBM이 rule-base를 이길 수 있는지 추가 실험했다.

전략:

```text
baseline_no_weight
severity_weighted
hard_case_weighted
event_balanced
substation_balanced
combined_context_weighted
combined_context_resampled
```

검증 원칙:

```text
1. 샘플링/가중치는 train split에만 적용
2. validation/holdout은 원분포 유지
3. 모델과 threshold는 validation에서 선택
4. holdout은 최종 평가에만 사용
5. rule-base component와 정답/식별자 계열은 feature에서 제외
```

핵심 결과:

| split | rule F1 | best LGBM F1 | best strategy | rule NDCG@R | best LGBM NDCG@R | 판정 |
|---|---:|---:|---|---:|---:|---|
| time holdout | 0.6290 | 0.6970 | hard_case_weighted | 0.7089 | 0.6962 | F1 개선, ranking 미달 |
| substation holdout | 0.7965 | 0.7748 | hard_case_weighted | 0.8050 | 0.7942 | rule-base 우세 |
| regime holdout | 0.7013 | 0.7634 | severity_weighted | 0.7797 | 0.7711 | F1 개선, ranking 미달 |

최종 해석:

```text
샘플링과 가중치는 효과가 있다.
특히 hard_case_weighted는 가능성이 있다.
하지만 새 설비 일반화인 substation holdout에서 rule-base를 넘지 못했다.
또한 priority 문제의 핵심인 ranking 지표 NDCG@R도 rule-base가 더 안정적이다.
```

따라서 현재 결론은 다음이다.

```text
rule-base = 운영 baseline
LGBM priority head = shadow score 또는 후속 후보
hybrid correction = 다음 단계 후보
```

## 11. holdout과 ranking 지표 해석

이번 프로젝트에서 holdout은 단순 train/test 분리가 아니라 운영 질문을 다르게 던지는 방식이다.

| split | 의미 | 운영 질문 |
|---|---|---|
| time holdout | 같은 설비의 미래 구간 | 같은 현장에서 미래에도 맞는가 |
| substation holdout | 특정 설비를 통째로 제외 | 처음 보는 설비에서도 맞는가 |
| regime holdout | 제조사/구성/계절/운전 조건 변화 | 다른 운전 조건에서도 맞는가 |

특히 운영 연동에서는 `substation holdout`이 중요하다.

이유:

```text
실제 서비스에서는 학습 때 보지 못한 설비나 기계실에 적용될 수 있기 때문이다.
```

ranking 지표인 `NDCG@R`도 중요하다.

의미:

```text
R = holdout 안의 실제 pre_fault 개수
Top R개를 뽑았을 때 더 급한 0-24h / 1-3d 케이스를 위쪽에 잘 배치했는지 평가
```

Priority 문제는 단순 회귀 MAE가 아니라 "무엇을 먼저 점검할 것인가"의 문제다. 따라서 F1이 좋아도 NDCG@R이 낮으면 운영 점검 순서 품질은 떨어질 수 있다.

## 12. 현재 handoff 기준

### 12.1 `model_handoff`

`model_handoff/heatgrid_ml_models_2026-06-25/`는 모델 파일 중심 전달 패키지다.

포함:

```text
anomaly/
  standard_scaler.joblib
  isolation_forest.joblib
  baseline_model_metadata.json

risk/
  lightgbm_risk_model.joblib
  risk_model_group_calibration.json
  risk_model_metadata.json

leadtime/
  lightgbm_leadtime_bucket_model_promoted.joblib
  leadtime_bucket_model_promoted_metadata.json

priority/
  priority_engine_tuned_metadata.json

docs/
  agent_preprocessed_input_columns.md
  agent_full_data_contract.md
```

특징:

```text
1. 모델 파일과 메타데이터 중심이다.
2. raw data에서 feature를 만드는 전체 코드가 포함되어 있지 않다.
3. 대상 프로젝트가 이미 동일 전처리/피처 생성 로직을 가지고 있을 때만 충분하다.
4. 실험 모델, legacy/paper_aligned 모델, 대량 score CSV는 제외했다.
```

### 12.2 `inference_handoff`

`inference_handoff/heatgrid_inference_package_2026-06-26/`는 실제 운영 프로젝트에 붙이기 위한 추론 패키지다.

포함:

```text
models/
contracts/
docs/
src/heatgrid_inference/
run_inference.py
PACKAGE_MANIFEST.json
```

역할:

```text
raw operational telemetry
-> 6 hour windowing
-> sensor statistics / missingness / time context / categorical one-hot
-> imputation and model feature ordering
-> anomaly score
-> risk probability and calibrated risk level
-> leadtime bucket
-> priority score and priority level
```

따라서 실제 외부 연동에는 `inference_handoff`를 넘기는 것이 맞다.

단, 이것도 재학습 패키지는 아니다.

재학습까지 필요하면 아래가 추가로 필요하다.

```text
raw dataset
label alignment notebooks
train/validation/holdout generation policy
experiment scripts and tuning grids
report notebooks
model promotion audit history
```

## 13. 왜 삭제하지 않고 보존했는가

레거시와 실험 파일을 삭제하지 않은 이유는 명확하다.

```text
1. 어떤 방향을 검토했고 왜 버렸는지 설명하는 증거다.
2. 나중에 성능이 흔들릴 때 다시 원인 분석을 시작할 기준점이다.
3. 보고서와 발표에서 "처음부터 잘 된 것처럼" 보이지 않게 시행착오를 투명하게 남긴다.
4. 모델 승격/보류 판단이 감이 아니라 실험 결과에 기반했음을 증명한다.
5. 향후 Autoencoder, Ranker, CatBoost, hybrid correction으로 확장할 때 비교 baseline이 된다.
```

즉 현재 repo의 레거시 정리는 파일 정리가 아니라 의사결정 기록 보존이다.

## 14. 현재 기준 공식/비공식 경계

### 공식으로 봐야 하는 것

```text
PREPROCESSING/osj/README.md
PREPROCESSING/osj/*.ipynb
PREPROCESSING/osj/pipeline_scripts/06_risk_calibration.py
PREPROCESSING/osj/pipeline_scripts/06_leadtime_model.py
PREPROCESSING/osj/pipeline_scripts/07_priority_engine.py
PREPROCESSING/docs/PROJECT_ML_STATUS.md
PREPROCESSING/docs/06_decision_summary.md
PREPROCESSING/docs/06_risk_official.md
PREPROCESSING/docs/06_leadtime_official.md
PREPROCESSING/docs/07_priority_engine.md
PREPROCESSING/docs/07_priority_engine_analysis.md
inference_handoff/heatgrid_inference_package_2026-06-26/
```

### 참고/실험으로 봐야 하는 것

```text
PREPROCESSING/osj/experiments/
PREPROCESSING/docs/06_test/
report/experiment_comparison/
report/priority_model_comparison/
priority_with_readme/
lgbm_priority_model/
```

### 레거시로 봐야 하는 것

```text
PREPROCESSING/legacy/
PREPROCESSING/osj/archive/
```

## 15. 다음 단계 제안

현재 기준으로 바로 모델을 교체하는 것은 적절하지 않다.

우선순위는 다음 순서가 맞다.

```text
1. rule-based priority_engine_v2_threshold48을 운영 baseline으로 유지
2. LGBM priority head는 shadow score로 붙여 추가 관찰
3. hybrid correction 실험
   - rule score를 중심으로 유지
   - threshold 근처에서만 ML correction 적용
   - correction 폭 제한
   - high/urgent guardrail 적용
4. 이후 더 강한 모델 후보 검토
   - LGBMRanker
   - CatBoost
   - two-stage model
   - ML-main + rule guardrail
```

단, ML이 rule-base를 폐기할 만큼 강하다고 판단하려면 최소 조건이 필요하다.

```text
1. substation holdout에서 rule-base보다 F1과 NDCG@R을 동시에 개선
2. regime holdout에서도 ranking 품질 유지
3. false positive 증가가 운영적으로 허용 가능한 수준
4. 누수 없는 raw inference 기준에서 재현
5. feature importance와 오류 케이스가 설명 가능
```

현재 실험 결과로는 이 조건을 아직 만족하지 못했다.

## 16. 최종 요약

현재 프로젝트는 여러 방향을 검토했지만, 최종 운영 기준은 아래로 정리된다.

```text
1. paper-aligned Autoencoder 시도는 레거시로 보존한다.
2. 구버전 wrapper/basic priority는 archive로 보존한다.
3. 06 실험/감사 코드는 experiments에 두고 공식 pipeline과 분리한다.
4. risk는 calibrated 공식본을 유지한다.
5. leadtime은 promoted 3-bucket 본을 공식으로 사용한다.
6. priority는 ML output을 입력으로 사용하는 rule-based v2_threshold48을 공식 baseline으로 유지한다.
7. 팀원 LGBM priority 모델은 현재 공식/운영 기준에서는 rule-base를 대체하지 못한다.
8. 외부 운영 연동은 `model_handoff`가 아니라 `inference_handoff` 기준으로 넘기는 것이 맞다.
```

한 줄 결론:

```text
이 프로젝트의 현재 핵심은 "ML 모델 하나"가 아니라,
raw data에서 anomaly/risk/leadtime 신호를 만들고
그 신호를 설명 가능한 priority decision layer로 연결하는 전체 추론 체인이다.
```

## 17. 주요 참조 파일

작업 흐름과 공식 기준:

```text
README.md
PREPROCESSING/osj/README.md
PREPROCESSING/osj/pipeline_scripts/README.md
PREPROCESSING/docs/PROJECT_ML_STATUS.md
PREPROCESSING/docs/06_decision_summary.md
PREPROCESSING/docs/06_risk_official.md
PREPROCESSING/docs/06_leadtime_official.md
PREPROCESSING/docs/07_priority_engine.md
PREPROCESSING/docs/07_priority_engine_analysis.md
```

레거시/아카이브 기준:

```text
PREPROCESSING/legacy/README.md
PREPROCESSING/legacy/docs/06_model_direction_decision.md
PREPROCESSING/legacy/docs/06_paper_aligned_review.md
PREPROCESSING/legacy/docs/06_paper_aligned_data_selection.md
PREPROCESSING/legacy/docs/06_paper_aligned_autoencoder.md
PREPROCESSING/legacy/docs/06_paper_aligned_event_eval.md
PREPROCESSING/legacy/docs/06_paper_aligned_feature_attribution.md
PREPROCESSING/osj/archive/README.md
PREPROCESSING/osj/experiments/README.md
```

실험 판단:

```text
PREPROCESSING/docs/06_audit_summary.md
PREPROCESSING/docs/06_group_calibration.md
PREPROCESSING/docs/06_feature_importance_audit.md
PREPROCESSING/docs/06_false_negative_deep_audit.md
PREPROCESSING/docs/06_manufacturer2_sh_fp_audit.md
PREPROCESSING/docs/06_promotion_decision.md
PREPROCESSING/docs/06_leadtime_promotion_decision.md
report/experiment_comparison/07_priority_threshold_sweep_summary.md
report/experiment_comparison/07_priority_v2_threshold48_promotion.md
report/experiment_comparison/07_priority_lgbm_regression_candidate_summary.md
```

Priority LGBM 비교:

```text
report/priority_model_comparison/priority_lgbm_vs_rule_report.md
report/priority_model_comparison/priority_with_readme_audit.md
report/priority_model_comparison/raw_priority_lgbm_vs_rule_report.md
report/priority_model_comparison/expanded_lgbm_priority_no_rule_report.md
report/priority_model_comparison/sampled_lgbm_priority_report.md
diary/2026-06-26_priority_model_comparison_diary.md
```

handoff:

```text
model_handoff/heatgrid_ml_models_2026-06-25/README.md
model_handoff/heatgrid_ml_models_2026-06-25/MANIFEST.json
inference_handoff/heatgrid_inference_package_2026-06-26/README.md
inference_handoff/heatgrid_inference_package_2026-06-26/docs/retraining_scope.md
inference_handoff/heatgrid_inference_package_2026-06-26/src/heatgrid_inference/scoring.py
```

작업 이력:

```text
diary/repository_migration_commit_history.md
diary/2026-06-23_ml_preprocessing_diary.md
diary/2026-06-24_ml_04_05_diary.md
diary/2026-06-24_ml_06_audit_diary.md
diary/2026-06-24_ml_06_diary.md
diary/2026-06-24_ml_06_resume_handoff.md
diary/2026-06-26_priority_model_comparison_diary.md
```
