# HeatFrid Agent ML 노트북 전체 수정·점검 전달 프롬프트

현재 HeatFrid Agent 프로젝트의 ML 파이프라인을 기존 `window + LightGBM risk classification` 방식에서 벗어나, PreDist 논문 방향에 맞춘 `Autoencoder 기반 Normal Behaviour Model + event-wise evaluation` 구조로 전환한다.

다만 최종 목적은 논문 재현이 아니라 **HeatFrid Agent가 지역난방 기계실 우선 점검 판단과 작업지시서 초안 생성을 수행할 수 있도록 ML 결과를 제공하는 것**이다.

따라서 논문 방식으로 ML core를 바꾸더라도, 기존 Agent / Priority Engine과의 데이터 계약은 반드시 유지해야 한다.

반드시 아래 논문을 기준으로 확인하고 수정하라.

논문 URL:  
https://arxiv.org/html/2511.14791v2

---

## 1. 수정 목적

현재 프로젝트는 PreDist v2 데이터를 사용하고 있지만, 기존 ML 방식은 논문 방식과 다르게 구성되어 있다.

기존 방식:

```text
Isolation Forest
→ 정상 패턴 대비 이상점수 산출

LightGBM
→ 고장신고 전 72시간 window와 normal window를 분류
→ risk_probability / risk_level 산출
```

하지만 이 방식은 다음 문제가 확인되었다.

```text
1. fault_report_time은 실제 고장 발생 시점이 아니라 신고 시점이다.
2. pre_fault window를 고정 72시간으로 자르는 방식은 라벨 불확실성이 크다.
3. normal window가 계절, 제조사, configuration, substation별 운전 regime 차이를 포함한다.
4. LightGBM이 고장 전 패턴이 아니라 운전 상태 차이를 학습할 위험이 있다.
5. manufacturer 2 / SH 그룹에서 holdout normal이 pre_fault보다 더 위험하게 평가되는 문제가 발생했다.
```

따라서 기존 `window + LightGBM` 방식을 더 이상 canonical ML 방식으로 유지하지 않는다.

수정 후 방향:

```text
PreDist 논문 방향에 맞춰
정상 행동 구간 선정
→ Autoencoder 기반 Normal Behaviour Model 학습
→ reconstruction error 기반 anomaly score 산출
→ criticality counter 적용
→ normal event / fault event 단위 평가
→ Agent와 Priority Engine에 전달 가능한 이상징후 결과 생성
```

---

## 2. 논문 방식 채택의 타당성

이번 수정은 단순히 논문을 따라 하기 위한 것이 아니다.

기존 `window + LightGBM` 방식은 고장신고 전 72시간을 `pre_fault`로 잘라 지도학습 분류를 수행했지만, PreDist의 `faults.csv` 시점은 실제 고장 발생 시점이 아니라 고장신고 시점이다. 따라서 고정된 pre_fault window를 정답 라벨처럼 사용하는 방식은 label uncertainty가 크다.

반면 PreDist 논문 방식은 정상 행동 구간을 기준으로 Normal Behaviour Model을 학습하고, 정상 행동에서 벗어난 정도를 reconstruction error와 anomaly score로 산출한다. 이 방식은 “고장 확률을 맞히는 분류기”보다 “정상 행동에서 벗어난 지속적인 이상징후를 찾는 구조”에 가깝다.

HeatFrid Agent의 목적도 고장을 확정하는 것이 아니라, 지역난방 기계실의 이상징후를 조기에 파악하고 우선 점검 대상과 작업지시서 초안을 생성하는 것이다. 따라서 논문 방식은 프로젝트 목적과 더 잘 맞는다.

논문 방식을 채택하는 이유는 다음과 같다.

```text
1. PreDist는 신고 기반 데이터라 window classification 라벨이 불안정할 수 있다.
2. Autoencoder 기반 Normal Behaviour Model은 정상 행동에서 벗어난 정도를 보므로 라벨 불확실성에 덜 민감하다.
3. normal event / fault event 단위 평가가 HeatFrid Agent의 우선 점검 목적과 더 잘 맞는다.
4. criticality counter를 통해 단발성 센서 튐을 줄이고 지속적인 이상징후를 중심으로 판단할 수 있다.
5. reconstruction error와 feature attribution 결과는 Agent의 판단 근거, 주요 이상 센서, 점검 항목 생성에 활용하기 좋다.
```

단, 논문 방식이 무조건 더 좋은 모델이라는 식으로 단정하지 마라.

반드시 아래 비교를 통해 검증하라.

```text
기존 방식:
- window + LightGBM
- window-level ROC-AUC / AP / F1 / FPR
- group-level FPR
- manufacturer 2 / SH normal 오탐 여부

논문 기반 방식:
- Autoencoder Normal Behaviour Model
- reconstruction error 기반 anomaly_score
- criticality counter
- normal event false alarm rate
- fault event detection rate
- detection lead time
- event-wise precision / recall / F-score
```

결과 문서에는 다음 관점을 반드시 포함하라.

```text
1. 기존 LightGBM 방식이 왜 불안정했는지
2. 논문 방식이 어떤 문제를 완화하는지
3. 논문 방식이 HeatFrid Agent 목적과 어떻게 연결되는지
4. 논문 방식에서도 남는 한계는 무엇인지
5. 논문 방식 결과를 Agent / Priority Engine 계약에 맞게 어떻게 변환했는지
```

주의할 점:

```text
- 논문 성능 수치를 그대로 우리 프로젝트 성능으로 주장하지 마라.
- 논문 방식도 반드시 현재 프로젝트 데이터와 코드에서 재현·비교해야 한다.
- 목표는 논문 재현이 아니라 HeatFrid Agent에 안정적인 이상징후 신호를 제공하는 것이다.
- 최종 결과는 anomaly_score, criticality_score, main_abnormal_features, risk_score, risk_level, priority_score 형태로 Agent 계약을 만족해야 한다.
```

---

## 3. 핵심 결정

기존 방식은 폐기 또는 삭제하지 말고, 비교용 legacy branch로 보존한다.

```text
기존 IsolationForest + LightGBM 방식
→ legacy / experimental branch

논문 기반 Autoencoder 방식
→ 새로운 canonical 후보
```

문서와 코드에서는 기존 방식을 다음처럼 표시한다.

```text
legacy_lgbm_window_classifier
experimental_lgbm_risk_branch
```

새로운 방식은 다음처럼 표시한다.

```text
paper_aligned_autoencoder_baseline
normal_behaviour_model
eventwise_fdd_baseline
```

---

## 4. 반드시 지켜야 할 표현 기준

이 프로젝트는 고장을 확정하지 않는다.

금지 표현:

```text
고장 확률
고장 발생 예측
고장 확정
정확한 고장 시점 예측
```

권장 표현:

```text
정상 행동에서 벗어난 정도
이상징후 점수
고장신고 전 이상 패턴 감지
우선 점검 판단을 위한 anomaly score
event detection signal
```

`faults.csv`의 시점은 실제 고장 발생 시점이 아니라 고장신고 시점이다.

따라서 report time 이전 test window는 “고장 발생 직전 구간”이 아니라 “고장신고 전 이상징후 감지 대상 구간”으로 표현한다.

---

## 5. 프로젝트 목적과 Agent 계약 유지

논문 방식은 ML core의 기준으로 사용한다.  
하지만 HeatFrid Agent의 서비스 방향성은 유지한다.

```text
논문 방식
→ 정상 행동 모델링
→ anomaly score
→ criticality counter
→ event-wise detection

HeatFrid Agent 목적
→ 기계실별 이상징후 판단
→ 우선 점검 대상 판단
→ 주요 이상 센서 추출
→ 점검 항목 생성
→ 작업지시서 초안 생성
→ 운영자 검토 후 전달
```

즉, 목표는 논문을 그대로 복제하는 것이 아니라, 논문 방식을 기반으로 Agent가 사용할 수 있는 안정적인 이상징후 결과를 만드는 것이다.

---

## 6. Agent에 전달해야 하는 기존 계약 유지

기존 Agent와 Priority Engine은 아래 형태의 정보를 기대한다.

논문 방식으로 모델을 바꾸더라도 최종 output schema는 이 계약을 만족해야 한다.

```text
substation_id
timestamp
event_id
event_type
manufacturer
configuration_type

anomaly_score
risk_score
risk_level
criticality_score
is_detected

main_abnormal_features
related_fault_history
related_disturbance_history
feature_explanation
```

단, 기존 LightGBM의 `risk_probability` 의미는 더 이상 고장 확률로 쓰지 않는다.

논문 방식 전환 후에는 아래처럼 의미를 재정의한다.

```text
risk_score
= anomaly_score, criticality_score, event detection 여부, 이력 정보, configuration type을 종합한 우선 점검 판단용 점수

risk_level
= low / medium / high / critical 형태의 운영자 표시용 위험 등급
```

즉, `risk_score`는 모델이 직접 예측한 고장 확률이 아니라, Agent와 Priority Engine에서 사용할 수 있도록 정규화한 운영 판단 점수다.

---

## 7. ML output과 Agent input의 연결 방식

논문 기반 Autoencoder 모델은 아래 값을 생성한다.

```text
reconstruction_error
anomaly_score
criticality_score
is_detected
detection_time
lead_time
main_abnormal_features
```

이 값은 그대로 Agent에 넘기는 것이 아니라, Priority Engine에서 운영 판단용 형태로 변환한다.

변환 흐름은 아래와 같다.

```text
Autoencoder output
→ reconstruction_error
→ anomaly_score
→ criticality_score
→ event detection signal

Priority Engine
→ anomaly_score + criticality_score + fault/task history + configuration_type 종합
→ risk_score
→ risk_level
→ priority_score

Agent
→ risk_score, risk_level, priority_score, 주요 이상 센서, 이력 정보 해석
→ 우선 점검 대상 종합 판단
→ 판단 근거 / 원인 후보 / 점검 항목 / 작업지시서 초안 생성
```

---

## 8. 기존 Agent 계약을 깨면 안 되는 이유

Agent는 단순히 anomaly score만 받아서는 운영 문서를 만들기 어렵다.

Agent가 필요한 것은 다음과 같다.

```text
1. 어느 기계실이 위험한지
2. 왜 위험하다고 판단했는지
3. 어떤 센서가 이상한지
4. 해당 기계실이 어떤 설비 구성인지
5. 과거 고장신고나 정비/작업 이력이 있는지
6. 어떤 점검 항목을 제안해야 하는지
7. 작업지시서 초안에 어떤 내용을 넣어야 하는지
```

따라서 ML output은 논문식 anomaly detection 결과만으로 끝나면 안 된다.

반드시 Agent가 사용할 수 있는 운영 판단 구조로 후처리해야 한다.

---

## 9. 먼저 할 일: 전체 노트북 점검

바로 코드를 수정하지 말고, 먼저 현재 노트북과 문서 구조를 확인하라.

특히 아래 파일들을 점검하라.

```text
PREPROCESSING/osj/06_risk_leadtime_model.ipynb
PREPROCESSING/osj/06_risk_leadtime_audit.ipynb
PREPROCESSING/osj/06_event_context_ablation.ipynb

PREPROCESSING/docs/06_risk_leadtime_model.md
PREPROCESSING/docs/06_risk_leadtime_audit.md
PREPROCESSING/docs/06_event_context_ablation.md
```

확인할 내용:

```text
1. 기존 window 생성 방식
2. pre_fault 라벨 생성 방식
3. normal 라벨 생성 방식
4. train / validation / holdout split 방식
5. Isolation Forest 사용 위치
6. LightGBM 학습 및 평가 방식
7. manufacturer 2 / SH 문제 진단 코드
8. 기존 결과 CSV 저장 경로
9. Agent / Priority Engine으로 전달되는 output schema
```

---

## 10. 논문 방식 요약 문서 작성

논문 URL을 직접 확인하고, 아래 내용을 정리하라.

```text
1. PreDist 데이터 구성
2. normal event와 fault event 사용 방식
3. Normal Behaviour Model 개념
4. Autoencoder 구조
5. reconstruction error 기반 anomaly score
6. criticality counter
7. event-wise evaluation
8. ARCANA 또는 feature attribution 방식
9. 논문 방식과 현재 프로젝트 방식의 차이
10. HeatFrid Agent에 적용할 수 있는 부분과 적용하지 않을 부분
```

작성 파일:

```text
PREPROCESSING/legacy/docs/06_paper_aligned_review.md
```

인터넷 접근이 불가능하면 임의로 구현하지 말고, 사용자에게 논문 PDF 또는 HTML 내용을 요청하라.

---

## 11. 기존 노트북 처리 방향

기존 노트북은 삭제하지 않는다.

대신 아래처럼 역할을 정리한다.

### 11.1 기존 LightGBM 노트북

```text
06_risk_leadtime_model.ipynb
```

역할 변경:

```text
기존 canonical 모델 노트북
→ legacy window-based LightGBM 실험 노트북
```

해야 할 일:

```text
1. 상단 markdown에 legacy 처리 사유 추가
2. window + LightGBM 방식의 한계 설명 추가
3. 기존 결과는 보존
4. 새로운 canonical 후보가 아님을 명시
5. paper-aligned baseline과 비교할 수 있도록 output schema만 정리
```

### 11.2 기존 audit 노트북

```text
06_risk_leadtime_audit.ipynb
```

역할 변경:

```text
LightGBM 문제 진단 노트북
→ legacy model failure analysis 노트북
```

해야 할 일:

```text
1. manufacturer 2 / SH 오탐 문제 정리
2. label / split / group shift / regime shift 문제 정리
3. 왜 논문 방식으로 전환하는지 근거 정리
4. 기존 진단 결과를 삭제하지 말고 보존
```

### 11.3 기존 event context ablation 노트북

```text
06_event_context_ablation.ipynb
```

역할 변경:

```text
LightGBM event context 실험 노트북
→ legacy ablation 기록
```

해야 할 일:

```text
1. event_days_only가 provisional canonical이었던 이유 정리
2. 하지만 최종 canonical에서 제외하는 이유 추가
3. 기존 ablation 결과 보존
4. paper-aligned baseline과 비교 대상으로 유지
```

---

## 12. 새로 만들 노트북

기존 방식을 억지로 뜯어고치지 말고, 논문 방향 baseline 노트북을 새로 만든다.

권장 노트북:

```text
PREPROCESSING/legacy/osj/06_paper_aligned_review.ipynb
PREPROCESSING/legacy/osj/06_paper_aligned_data_selection.ipynb
PREPROCESSING/legacy/osj/06_paper_aligned_autoencoder.ipynb
PREPROCESSING/legacy/osj/06_paper_aligned_event_eval.ipynb
PREPROCESSING/legacy/osj/06_paper_aligned_feature_attribution.ipynb
PREPROCESSING/legacy/osj/06_paper_aligned_agent_contract.ipynb
```

각 노트북 역할:

### 12.1 06_paper_aligned_review.ipynb

목적:

```text
논문 방식과 현재 프로젝트 방식 차이 정리
```

산출물:

```text
PREPROCESSING/legacy/docs/06_paper_aligned_review.md
```

### 12.2 06_paper_aligned_data_selection.ipynb

목적:

```text
논문 방식에 맞는 normal / fault event data selection 구성
```

반드시 포함할 내용:

```text
- operational_data 로딩
- faults.csv 로딩
- disturbances.csv 로딩
- normal_events.csv 로딩
- feature_descriptions.csv 로딩
- configuration_types.csv 로딩
- fault event별 test window 구성
- normal event별 평가 구간 구성
- fault/task/disturbance 주변 구간 normal 학습에서 제외
- manufacturer/configuration_type/substation 분포 확인
```

산출물 예시:

```text
data/processed/paper_aligned/event_windows.csv
data/processed/paper_aligned/normal_training_windows.csv
data/processed/paper_aligned/fault_test_windows.csv
data/processed/paper_aligned/normal_event_eval_windows.csv
```

### 12.3 06_paper_aligned_autoencoder.ipynb

목적:

```text
Autoencoder 기반 Normal Behaviour Model 최소 baseline 구현
```

구현 기준:

```text
- 처음부터 복잡한 모델 금지
- 재현 가능한 최소 Autoencoder 구현
- 정상 행동 학습 구간으로만 학습
- reconstruction error 산출
- anomaly_score 산출
```

출력 컬럼:

```text
substation_id
timestamp
event_id
event_type
manufacturer
configuration_type
reconstruction_error
anomaly_score
```

산출물 예시:

```text
data/processed/paper_aligned/ae_anomaly_scores.csv
data/processed/paper_aligned/ae_model_metrics.csv
```

### 12.4 06_paper_aligned_event_eval.ipynb

목적:

```text
window-level 분류 평가가 아니라 event-wise evaluation 구현
```

평가 기준:

```text
normal event:
  - false alarm 여부
  - false alarm count
  - normal event accuracy 또는 reliability

fault event:
  - report time 이전 test window 안에서 감지했는지
  - detected 여부
  - detection lead time
  - event-wise precision / recall / F-score
```

산출물 예시:

```text
data/processed/paper_aligned/ae_event_eval_summary.csv
data/processed/paper_aligned/ae_fault_event_detection.csv
data/processed/paper_aligned/ae_normal_event_false_alarm.csv
```

### 12.5 06_paper_aligned_feature_attribution.ipynb

목적:

```text
Agent가 사용할 주요 이상 센서 후보 추출
```

처음부터 ARCANA를 완전 구현하기 어렵다면 최소 구현으로 시작한다.

최소 구현:

```text
- feature별 reconstruction error contribution
- 정상 평균 대비 feature deviation
- anomaly window 내 상위 이상 feature 추출
- feature_descriptions.csv와 연결
```

출력 컬럼:

```text
substation_id
timestamp
event_id
feature_name
feature_description
sensor_group
contribution_score
deviation_score
rank
```

산출물 예시:

```text
data/processed/paper_aligned/ae_feature_attribution.csv
```

### 12.6 06_paper_aligned_agent_contract.ipynb

목적:

```text
논문 방식 Autoencoder 결과를 기존 Agent / Priority Engine 계약에 맞게 변환
```

해야 할 일:

```text
1. Autoencoder output 로딩
2. feature attribution 결과 로딩
3. fault/task history context 연결
4. configuration_type 연결
5. Priority Engine용 risk_score / risk_level / priority_score 계산
6. Agent 입력용 JSON 또는 CSV schema 생성
7. 기존 Agent 계약과 호환되는지 검증
```

산출물 예시:

```text
data/processed/paper_aligned/agent_ml_contract.csv
data/processed/paper_aligned/priority_input.csv
data/processed/paper_aligned/agent_input_examples.json
```

---

## 13. criticality counter 구현

단일 시점 reconstruction error만으로 detection을 판단하지 않는다.

논문 방향에 맞춰 criticality counter를 구현한다.

목적:

```text
1. 단발성 point anomaly 완화
2. 일정 시간 이상 이상점수가 지속될 때 detection으로 판단
3. 운영자에게 불필요한 오탐을 줄임
```

구현 요소:

```text
anomaly_threshold
criticality_threshold
counter_increase_rule
counter_decay_rule
is_detected
detection_time
lead_time
```

산출물에는 반드시 다음 컬럼을 포함한다.

```text
substation_id
timestamp
event_id
anomaly_score
criticality_score
is_detected
```

---

## 14. Priority Engine 수정 방향

Priority Engine은 기존 LightGBM risk_probability에 의존하지 않도록 수정한다.

새 Priority Engine은 아래 정보를 사용한다.

```text
anomaly_score
criticality_score
is_detected
main_abnormal_features
fault_history_count
recent_fault_history
recent_disturbance_history
configuration_type
manufacturer
substation_id
```

출력은 기존과 동일하게 유지한다.

```text
substation_id
priority_score
priority_rank
risk_score
risk_level
priority_reason
```

`priority_reason`에는 아래 내용을 포함한다.

```text
- 정상 행동 대비 이상 정도
- criticality 지속 여부
- 주요 이상 센서
- 과거 고장신고 이력
- 최근 정비/작업 이력
- 기계실 설비 구성 유형
```

---

## 15. 기존 LightGBM 방식과 비교

논문 기반 AE baseline을 만든 뒤 기존 LightGBM 방식과 비교한다.

비교 목적은 단순 성능 경쟁이 아니라, HeatFrid Agent가 사용할 수 있는 안정적인 이상징후 신호를 어느 방식이 더 잘 제공하는지 판단하는 것이다.

비교 항목:

```text
1. 기존 LGBM window-level ROC-AUC / AP / F1 / FPR
2. 기존 LGBM group-level FPR
3. 기존 LGBM manufacturer 2 / SH normal 오탐 여부
4. AE event-wise fault detection rate
5. AE normal event false alarm rate
6. AE lead time
7. manufacturer/configuration_type별 성능
8. Agent에 넘길 output의 안정성
```

비교 결과 문서:

```text
PREPROCESSING/legacy/docs/06_model_direction_decision.md
```

문서에 반드시 포함할 결론:

```text
기존 window + LightGBM 방식은 PreDist 데이터의 신고 기반 label 특성 때문에
label/split/regime shift 문제가 발생할 수 있으므로 canonical에서 제외한다.

논문 방향의 Autoencoder 기반 Normal Behaviour Model은 정상 행동에서 벗어난 정도를 탐지하고,
event-wise로 평가할 수 있어 HeatFrid Agent의 이상징후 탐지 목적에 더 적합하다.

다만 HeatFrid Agent의 최종 목적은 논문 재현이 아니라 우선 점검 판단과 작업지시서 초안 생성을 위한 Agent 입력 생성이다.
따라서 Autoencoder 결과는 Priority Engine을 통해 risk_score, risk_level, priority_score로 변환되어 Agent 계약을 만족해야 한다.
```

---

## 16. HeatFrid Agent 연결용 최종 output schema

새로운 ML 결과는 Agent와 Priority Engine에서 사용할 수 있어야 한다.

최종 ML output schema를 아래처럼 정리하라.

```text
substation_id
timestamp
event_id
event_type
manufacturer
configuration_type

reconstruction_error
anomaly_score
criticality_score
is_detected
detection_time
lead_time

risk_score
risk_level
priority_score
priority_rank
priority_reason

main_abnormal_features
related_fault_history
related_disturbance_history
feature_explanation
```

Priority Engine은 아래 정보를 사용한다.

```text
anomaly_score
criticality_score
is_detected
main_abnormal_features
configuration_type
fault/task history
substation_id
manufacturer
```

Agent는 아래 정보를 사용한다.

```text
정상 행동에서 벗어난 정도
criticality 상태
주요 이상 센서
기계실 설비 구성 유형
고장신고 이력
정비/작업 이력
센서 설명
risk_score
risk_level
priority_score
priority_reason
```

---

## 17. Agent 출력은 기존 방향 유지

Agent는 논문 방식으로 바뀐 ML 결과를 바탕으로 아래 결과를 계속 생성해야 한다.

```text
우선 점검 대상
판단 근거
원인 후보
주요 이상 센서
점검 항목
작업지시서 초안
운영자 검토용 요약
```

Agent가 사용하면 안 되는 표현:

```text
고장 확정
고장 발생 확률
자동 출동
자동 조치
자동 제어
```

Agent가 사용해야 하는 표현:

```text
이상징후
정상 행동에서 벗어난 정도
우선 점검 필요 가능성
점검 권장
운영자 검토 필요
```

---

## 18. 문서화 기준

작업 후 아래 문서를 작성하거나 수정한다.

```text
PREPROCESSING/legacy/docs/06_paper_aligned_review.md
PREPROCESSING/legacy/docs/06_paper_aligned_data_selection.md
PREPROCESSING/legacy/docs/06_paper_aligned_autoencoder.md
PREPROCESSING/legacy/docs/06_paper_aligned_event_eval.md
PREPROCESSING/legacy/docs/06_paper_aligned_feature_attribution.md
PREPROCESSING/legacy/docs/06_paper_aligned_agent_contract.md
PREPROCESSING/legacy/docs/06_model_direction_decision.md
```

각 문서에는 다음 내용을 포함한다.

```text
1. 기존 LightGBM 방식의 문제
2. 논문 방식으로 전환한 이유
3. 논문 방식이 HeatFrid Agent 목적과 연결되는 이유
4. data selection 기준
5. Autoencoder baseline 구조
6. anomaly score 계산 방식
7. criticality counter 기준
8. event-wise evaluation 결과
9. 기존 방식과 비교 결과
10. 기존 Agent / Priority Engine 계약 유지 방식
11. Agent / Priority Engine 전달 output schema
12. 남은 한계와 다음 단계
```

---

## 19. 작업 순서

아래 순서로 진행하라.

```text
1. 논문 URL 확인
2. 기존 06 관련 노트북 전체 점검
3. 기존 LightGBM 노트북을 legacy로 정리
4. paper-aligned review 문서 작성
5. paper-aligned data selection 노트북 생성
6. Autoencoder baseline 노트북 생성
7. anomaly score 산출
8. criticality counter 구현
9. event-wise evaluation 구현
10. feature attribution 최소 구현
11. Agent / Priority Engine 계약 변환 노트북 생성
12. 기존 LightGBM 결과와 비교
13. 모델 방향 결정 문서 작성
14. Agent / Priority Engine output schema 정리
```

---

## 20. 주의사항

- 기존 결과 파일을 삭제하지 마라.
- 기존 LightGBM 코드를 실패로 단정하지 말고 legacy 실험으로 보존하라.
- 하지만 canonical ML 방식은 논문 기반 Autoencoder 방향으로 전환한다.
- 논문 내용을 확인하지 않고 임의로 논문 방식이라고 쓰지 마라.
- 인터넷 접근이 안 되면 사용자에게 논문 PDF 또는 내용을 요청하라.
- 논문 성능 수치를 그대로 우리 프로젝트 성능으로 주장하지 마라.
- 논문 방식도 반드시 현재 프로젝트 데이터와 코드에서 재현·비교해야 한다.
- 고장 확률이라는 표현을 쓰지 마라.
- output은 anomaly score, criticality score, event detection signal 중심으로 정리하라.
- 단, Agent 계약을 위해 risk_score, risk_level, priority_score는 반드시 제공하라.
- risk_score는 고장 확률이 아니라 운영 판단용 이상위험 점수로 정의하라.
- 프로젝트명은 HeatFrid Agent로 통일하라.
- Copilot 표현은 사용하지 마라.
- 운영자 검토 없는 자동 제어, 자동 출동, 자동 발송은 구현하지 마라.
- 초보자가 이해할 수 있도록 변수명, 함수명, markdown 설명은 직관적으로 작성하라.

---

## 21. 첫 응답 형식

바로 코드를 수정하지 말고 먼저 아래 형식으로 계획을 제시하라.

```text
1. 논문 방식으로 전환해야 하는 이유
2. 논문 방식으로 바꿀 ML core
3. 유지해야 할 HeatFrid Agent 계약
4. 기존 output schema와 새 output schema 비교
5. Priority Engine 수정 방향
6. Agent 연결부에서 깨질 수 있는 부분
7. 기존 방식에서 legacy로 남길 파일
8. 새로 만들 노트북 목록
9. 새로 만들 문서 목록
10. 수정할 기존 노트북 목록
11. 구현 순서
12. 예상 산출물
13. 위험 요소
14. 사용자 확인이 필요한 부분
```

내가 승인하면 그 다음 코드 수정에 들어가라.

