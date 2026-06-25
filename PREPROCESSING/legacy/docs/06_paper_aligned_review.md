# 06-P. paper-aligned review 문서

이 문서는 기존 `window + LightGBM` 06 흐름과 `Autoencoder 기반 Normal Behaviour Model + event-wise evaluation` 방향의 차이를 정리한 아카이브 문서다.

참고 논문:

- Roelofs et al., *Enabling Predictive Maintenance in District Heating Substations: A Labelled Dataset and Fault Detection Evaluation Framework based on Service Data*, arXiv:2511.14791v2, 2026-04-17
- URL: https://arxiv.org/html/2511.14791v2

## 목적

- 왜 기존 06을 canonical에서 legacy로 내리는지 설명
- 논문 정렬 방식과 현재 프로젝트 목적의 공통점과 차이를 분리
- HeatGrid Agent와 Priority Engine 계약을 유지하면서 어떤 ML core를 바꿔야 하는지 정리

## 논문 핵심 요약

논문 기준 PreDist 구성:

- 93개 substation
- 제조사 2종(M1, M2)
- 10분 해상도 운영 시계열
- maintenance / incident report annotation
- pre-defined normal event 제공

논문은 fault classifier를 제안하는 구조가 아니라, `Autoencoder 기반 normal behaviour model`과 event-wise 평가 프레임워크를 제시한다.

핵심 방법론:

1. fault 및 normal event를 event 단위로 선택
2. 각 event마다 사전 정상 행동 구간을 정리
3. Autoencoder를 정상 행동 데이터에 학습
4. reconstruction error 기반 anomaly score 계산
5. point anomaly 억제를 위해 criticality counter 적용
6. normal event false alarm, anomaly event detection, lead time을 event-wise로 평가
7. ARCANA로 top abnormal features를 해석

논문에서 확인한 구체 기준:

- 정상 행동 학습용 데이터는 event 전 최대 2년, 최소 14일 조건으로 선정
- training 구간 안 report / maintenance 영향 구간은 추가로 제거
- feature는 training 기간 기준 상수 컬럼과 80% 이상 결측 컬럼을 제외
- 나머지 결측은 training 평균값으로 대체
- anomaly score threshold는 training score 99% 분위수 기준
- 평가 test window는 incident report 이전 7일
- reliability는 event-wise F-score 계열로 계산
- detection 시점은 criticality threshold를 처음 넘은 시점으로 정의

## 현재 프로젝트와의 차이

기존 프로젝트 06:

```text
window feature
+ Isolation Forest anomaly_score
+ fault_report_time 기준 pre_fault 라벨
-> LightGBM
-> risk_probability
```

논문 정렬 06-P:

```text
normal event selection
-> normal behaviour model
-> reconstruction error
-> criticality counter
-> event-wise detection / false alarm / lead time
-> Agent contract mapping
```

차이의 핵심은 다음과 같다.

1. 기존 06은 window-level supervised 분류다.
2. 논문 방식은 정상 행동 기준 anomaly detection이다.
3. 기존 06은 `fault report 이전 72h`를 라벨처럼 사용한다.
4. 논문 방식은 exact onset을 가정하지 않고 report 전 actionable window 기준으로 평가한다.

## 왜 전환하는가

현재 프로젝트에서 확인된 문제는 논문 방향 전환 이유와 직접 연결된다.

- `faults.csv` 시점은 onset이 아니라 report time이다.
- fixed pre-fault window는 라벨 불확실성이 크다.
- manufacturer / configuration / substation regime 차이가 크다.
- 실제로 `manufacturer 2 / SH` holdout normal이 pre_fault보다 높게 뜨는 failure가 있었다.

따라서 기존 LightGBM은 성능 수치보다 먼저 라벨 구조와 regime shift에 흔들릴 가능성이 크다.

반면 논문 방식은 다음을 완화한다.

- onset 불명확성: event-wise detection / lead time으로 완화
- regime 차이: event별 normal behaviour 학습으로 완화
- point anomaly 오탐: criticality counter로 완화
- black-box 해석 문제: ARCANA 또는 대체 attribution으로 완화

## 그대로 가져올 것

- normal event / fault event 기반 평가 관점
- normal behaviour model 중심 구조
- reconstruction error + criticality counter
- event-wise false alarm / detection / earliness
- 주요 이상 feature 추출

## 그대로 가져오지 않을 것

- 논문 성능 수치를 프로젝트 성능처럼 사용하지 않는다.
- 논문 구현을 그대로 복제하는 대신 현재 데이터 구조와 계약에 맞춰 축소 적용한다.
- `risk_score`를 모델의 고장 확률처럼 사용하지 않는다.

## Agent / Priority Engine 계약 유지 방식

논문 기준 anomaly output을 그대로 종료하지 않고 아래 계약으로 변환한다.

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

여기서 의미는 다음처럼 바뀐다.

- `anomaly_score`: 정상 행동에서 벗어난 정도
- `criticality_score`: 지속성 반영 점수
- `risk_score`: 운영 우선 점검 판단용 통합 점수
- `risk_level`: 운영자 표시용 등급

## 결론

```text
1. 기존 LightGBM 06 체인을 다시 메인 체인으로 사용한다.
2. 이 paper-aligned 묶음은 `PREPROCESSING/legacy` 아래 실험 기록으로 보존한다.
3. 필요하면 06-P1 ~ 06-P5 순서로 다시 참조한다.
4. 최종 목표는 논문 재현이 아니라 Agent가 쓸 수 있는 안정적인 이상징후 계약이다.
```
