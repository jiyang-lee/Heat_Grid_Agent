# HeatFrid Repair 실행 계획

이 문서는 `PREPROCESSING/legacy/docs/heatfrid_repair_prompt.md` 기준으로 현재 프로젝트를 어떻게 수정할지 정리한 실행 계획이다.

목표는 기존 `window + LightGBM risk classification` 중심 06 흐름을 `paper-aligned Autoencoder Normal Behaviour Model + event-wise evaluation` 구조로 전환하되, Agent / Priority Engine 계약은 유지하는 것이다.

## 1. 논문 방식으로 전환해야 하는 이유

현재 06 canonical은 이미 `lgbm_risk_06_event_days_v1`까지 보강됐지만, 아래 한계가 남아 있다.

- `faults.csv`의 시점은 실제 고장 발생 시점이 아니라 신고 시점이다.
- `pre_fault = report_time 이전 72h` 라벨은 불확실성이 크다.
- `normal`은 계절, 제조사, configuration, substation별 regime 차이를 포함한다.
- `manufacturer 2 / SH` holdout normal이 pre_fault처럼 보이는 문제가 남아 있다.
- 현재 방식은 “고장 확정”이 아니라 “운전 상태 차이”를 과학습할 위험이 있다.

따라서 06의 ML core는 `정상행동모델 기반 anomaly detection`으로 바꾸고, 고장신고 전후는 event-wise 평가와 Priority Engine 해석에서 다루는 방향이 더 맞다.

## 2. 바뀌는 ML core

기존 core:

```text
03 window 생성
04 feature 선택
05 Isolation Forest anomaly_score
06 LightGBM risk classification
```

변경 후 core:

```text
03/04에서 준비한 운영 시계열과 feature를 재사용
06_paper_aligned_data_selection
06_paper_aligned_autoencoder
06_paper_aligned_event_eval
06_paper_aligned_feature_attribution
06_paper_aligned_agent_contract
```

새 canonical 개념:

- 정상 구간만으로 Autoencoder 학습
- reconstruction error 기반 anomaly score
- criticality counter로 지속 이상 탐지
- normal event / fault event 단위 평가
- 최종적으로 Agent / Priority Engine이 쓸 `risk_score`, `risk_level`, `priority_score` 생성

## 3. 유지해야 할 HeatFrid Agent 계약

ML core는 바뀌어도 아래 계약은 유지해야 한다.

- Agent는 anomaly 자체만 받는 것이 아니라 운영용 해석 결과를 받아야 한다.
- Priority Engine은 `risk_probability`에 강결합되면 안 된다.
- 최종 출력은 기계실 단위 우선점검 판단과 작업지시서 초안 생성에 연결돼야 한다.

유지 대상 개념:

```text
substation_id
timestamp
manufacturer
configuration_type
main_abnormal_features
related_fault_history
related_disturbance_history
risk_score
risk_level
priority_score
priority_reason
```

## 4. 기존 output schema와 새 output schema 비교

기존 06 중심:

```text
anomaly_score
risk_probability
risk_level
main_abnormal_features
related_fault_history
related_disturbance_history
```

새 canonical 목표:

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

핵심 차이:

- `risk_probability` 중심 분류 출력에서 벗어난다.
- `anomaly_score + criticality_score + event detection`을 먼저 만든다.
- `risk_score`, `risk_level`은 Priority Engine에서 재정의한다.

## 5. Priority Engine 수정 방향

Priority Engine은 기존 `risk_probability` 중심 해석에서 아래 조합 중심으로 바뀌어야 한다.

입력 후보:

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

출력 유지:

```text
substation_id
priority_score
priority_rank
risk_score
risk_level
priority_reason
```

정의 변경:

- `risk_score`: 고장 확률이 아니라 운영 위험 점수
- `risk_level`: 점검 우선 등급
- `priority_score`: 작업 우선순위 계산 결과

## 6. Agent 연결부에서 바뀌는 부분

Agent는 아래 입력을 더 직접 활용하게 된다.

- reconstruction error 기반 이상 근거
- criticality counter 상태
- event detection 여부
- 주요 이상 feature와 설명
- configuration / fault history / disturbance history

Agent 쪽에서 유지해야 할 표현:

- 이상징후
- 정상행동에서 벗어난 정도
- 우선 점검 필요 가능성
- 점검 권장
- 운영자 확인 필요

금지 표현:

- 고장 확정
- 고장 발생 예측 확정
- 자동 제어
- 자동 출동

## 7. legacy로 둘 파일

아래 파일은 삭제하지 않고 `legacy / comparison baseline`으로 보존한다.

- [06_risk_leadtime_model.ipynb](/C:/Project3/HeatGrid_Agent/PREPROCESSING/osj/06_risk_leadtime_model.ipynb)
- [06_risk_leadtime_audit.ipynb](/C:/Project3/HeatGrid_Agent/PREPROCESSING/osj/06_risk_leadtime_audit.ipynb)
- [06_event_context_ablation.ipynb](/C:/Project3/HeatGrid_Agent/PREPROCESSING/osj/06_event_context_ablation.ipynb)
- [06_risk_leadtime_model.md](/C:/Project3/HeatGrid_Agent/PREPROCESSING/docs/06_risk_leadtime_model.md)
- [06_risk_leadtime_audit.md](/C:/Project3/HeatGrid_Agent/PREPROCESSING/docs/06_risk_leadtime_audit.md)
- [06_event_context_ablation.md](/C:/Project3/HeatGrid_Agent/PREPROCESSING/docs/06_event_context_ablation.md)

legacy 역할:

- 기존 LightGBM 방식 성능/한계 비교
- `manufacturer 2 / SH` failure evidence 보존
- paper-aligned 방향 전환 근거 제공

## 8. 새로 만들 노트북 목록

- `PREPROCESSING/legacy/osj/06_paper_aligned_review.ipynb`
- `PREPROCESSING/legacy/osj/06_paper_aligned_data_selection.ipynb`
- `PREPROCESSING/legacy/osj/06_paper_aligned_autoencoder.ipynb`
- `PREPROCESSING/legacy/osj/06_paper_aligned_event_eval.ipynb`
- `PREPROCESSING/legacy/osj/06_paper_aligned_feature_attribution.ipynb`
- `PREPROCESSING/legacy/osj/06_paper_aligned_agent_contract.ipynb`

각 역할:

- `06_paper_aligned_review`
  - 논문 방식과 현재 방식 차이 정리
- `06_paper_aligned_data_selection`
  - normal/fault event 단위 학습/평가 구간 구성
- `06_paper_aligned_autoencoder`
  - 정상행동모델 baseline 학습
- `06_paper_aligned_event_eval`
  - event-wise detection / false alarm / lead time 평가
- `06_paper_aligned_feature_attribution`
  - anomaly explanation 최소 구현
- `06_paper_aligned_agent_contract`
  - Agent / Priority Engine 입력 스키마 정리

## 9. 새로 만들 문서 목록

- `PREPROCESSING/legacy/docs/06_paper_aligned_review.md`
- `PREPROCESSING/legacy/docs/06_paper_aligned_data_selection.md`
- `PREPROCESSING/legacy/docs/06_paper_aligned_autoencoder.md`
- `PREPROCESSING/legacy/docs/06_paper_aligned_event_eval.md`
- `PREPROCESSING/legacy/docs/06_paper_aligned_feature_attribution.md`
- `PREPROCESSING/legacy/docs/06_paper_aligned_agent_contract.md`
- `PREPROCESSING/legacy/docs/06_model_direction_decision.md`

## 10. 수정할 기존 파일 목록

문서:

- [ML_NOTEBOOK_PLAN.md](/C:/Project3/HeatGrid_Agent/PREPROCESSING/docs/ML_NOTEBOOK_PLAN.md)
  - 06 canonical을 paper-aligned 구조로 갱신
- [heatfrid_repair_prompt.md](/C:/Project3/HeatGrid_Agent/PREPROCESSING/legacy/docs/heatfrid_repair_prompt.md)
  - 원문은 유지, 필요시 UTF-8 표시만 점검
- [2026-06-24_ml_06_diary.md](/C:/Project3/HeatGrid_Agent/diary/2026-06-24_ml_06_diary.md)
  - canonical 표현을 legacy/provisional로 수정

노트북:

- [03_preprocess_windows.ipynb](/C:/Project3/HeatGrid_Agent/PREPROCESSING/osj/03_preprocess_windows.ipynb)
  - window classifier 중심 설명 축소
  - paper-aligned data selection 입력 준비 단계로 재정의
- [04_feature_selection.ipynb](/C:/Project3/HeatGrid_Agent/PREPROCESSING/osj/04_feature_selection.ipynb)
  - LightGBM 전용 표현 축소
- [05_baseline_anomaly_model.ipynb](/C:/Project3/HeatGrid_Agent/PREPROCESSING/osj/05_baseline_anomaly_model.ipynb)
  - Isolation Forest를 legacy anomaly baseline으로 표기
- `06_* legacy` 3개
  - canonical 표현 제거
  - 비교 baseline 역할 명시

## 11. 구현 순서

1. `ML_NOTEBOOK_PLAN.md`를 새 canonical 구조로 수정
2. 기존 `06_*` LightGBM 문서/노트북을 legacy로 재분류
3. `06_paper_aligned_review.ipynb/.md` 작성
4. `06_paper_aligned_data_selection.ipynb/.md` 작성
5. `06_paper_aligned_autoencoder.ipynb/.md` 작성
6. `criticality counter` 로직 포함
7. `06_paper_aligned_event_eval.ipynb/.md` 작성
8. `06_paper_aligned_feature_attribution.ipynb/.md` 작성
9. `06_paper_aligned_agent_contract.ipynb/.md` 작성
10. `06_model_direction_decision.md`로 legacy vs canonical 비교 결론 작성
11. diary와 handoff 문서 갱신

## 12. 예상 산출물

새 processed 경로 권장:

```text
data/processed/paper_aligned/event_windows.csv
data/processed/paper_aligned/normal_training_windows.csv
data/processed/paper_aligned/fault_test_windows.csv
data/processed/paper_aligned/normal_event_eval_windows.csv

data/processed/paper_aligned/ae_anomaly_scores.csv
data/processed/paper_aligned/ae_model_metrics.csv
data/processed/paper_aligned/ae_event_eval_summary.csv
data/processed/paper_aligned/ae_fault_event_detection.csv
data/processed/paper_aligned/ae_normal_event_false_alarm.csv
data/processed/paper_aligned/ae_feature_attribution.csv

data/processed/paper_aligned/agent_ml_contract.csv
data/processed/paper_aligned/priority_input.csv
data/processed/paper_aligned/agent_input_examples.json
```

## 13. 위험 요소

- 논문 URL 내용 검증 없이 구현 세부를 단정하면 안 된다.
- 현재 프로젝트 표기가 `HeatGrid`와 `HeatFrid`로 섞여 있다.
- 기존 `risk_probability`에 의존하는 downstream 코드가 있으면 연결부 수정이 커진다.
- Autoencoder 학습 대상 normal 구간 정의가 또 흔들리면 legacy와 같은 regime shift 문제가 반복될 수 있다.
- feature attribution은 초기에 최소 구현으로 제한해야 한다.

## 14. 사용자 확인이 필요한 부분

- 프로젝트 표준 명칭을 `HeatFrid Agent`로 통일할지
- 논문 HTML만 기준으로 갈지, PDF 원문 확인이 필요한지
- Priority Engine 코드가 현재 어디까지 구현돼 있는지
- Agent 입력 스키마가 실제 코드 기준인지 문서 기준인지
- legacy 06 결과 파일을 그대로 남길지, 별도 `legacy_*` 경로로 복사할지

## 결론

이번 수정은 06을 조금 다듬는 수준이 아니다.

해야 할 일은 다음 두 축이다.

- 기존 LightGBM 06 체인을 `legacy comparison baseline`으로 보존
- 논문 정렬 Autoencoder 기반 06 canonical 체인을 새로 구축

즉, 지금부터의 수정은 “보강”이 아니라 “모델 방향 전환 + Agent 계약 재연결” 작업으로 봐야 한다.

