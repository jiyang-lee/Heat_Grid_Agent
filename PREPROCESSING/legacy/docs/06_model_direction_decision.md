# 06 모델 방향 결정

이 문서는 06번 ML 단계의 canonical 방향을 무엇으로 둘지 고정하기 위해 작성한다.

결론은 다음과 같다.

```text
당시 비교 baseline:
  window + Isolation Forest + LightGBM

canonical candidate:
  paper-aligned Autoencoder Normal Behaviour Model
  + criticality counter
  + event-wise evaluation
  + Agent / Priority Engine contract mapping
```

## 결정 배경

기존 `window + LightGBM` 체인은 비교 실험으로는 유효했지만, canonical로 유지하기에는 한계가 분명했다.

- `faults.csv` 시점은 실제 고장 발생 시점이 아니라 신고 시점이다.
- 고정 `pre_fault` window 분류는 라벨 불확실성이 크다.
- 제조사, configuration, substation별 운전 regime 차이를 LightGBM이 학습할 위험이 있다.
- 실제로 `manufacturer 2 / SH` holdout normal이 pre_fault보다 높게 평가되는 문제가 확인됐다.

## 왜 paper-aligned 방향인가

논문 기준 구조는 supervised fault classifier보다 다음 목적에 더 맞는다.

- 정상 행동 기준 이상징후 탐지
- 지속적인 이상 구간 강조
- event 단위 false alarm / detection / lead time 평가
- feature attribution 기반 운영 설명 가능성 확보

이 프로젝트의 목적도 고장 확정이 아니라 우선 점검 판단용 신호 제공이다.
따라서 `normal behaviour model -> anomaly signal -> 운영 판단 점수` 흐름이 더 적합하다.

## 유지할 것

ML core는 바뀌어도 아래 계약은 유지한다.

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

## legacy 자산 처리

아래 파일은 삭제하지 않고 `legacy / comparison baseline`으로 남긴다.

- `PREPROCESSING/osj/06_risk_leadtime_model.ipynb`
- `PREPROCESSING/osj/06_risk_leadtime_audit.ipynb`
- `PREPROCESSING/osj/06_event_context_ablation.ipynb`
- `PREPROCESSING/docs/06_risk_leadtime_model.md`
- `PREPROCESSING/docs/06_risk_leadtime_audit.md`
- `PREPROCESSING/docs/06_event_context_ablation.md`

역할은 다음과 같다.

- LightGBM 방식 실패 원인 보존
- paper-aligned 전환 근거 보존
- 향후 비교 baseline 제공

## 새 canonical 작업 순서

```text
06_paper_aligned_review
06_paper_aligned_data_selection
06_paper_aligned_autoencoder
06_paper_aligned_event_eval
06_paper_aligned_feature_attribution
06_paper_aligned_agent_contract
```

## 표현 규칙

금지:

- 고장 확률
- 고장 확정
- 정확한 고장 시점 예측

권장:

- 정상 행동에서 벗어난 정도
- 이상징후 점수
- 고장신고 전 이상 패턴 감지
- 우선 점검 판단용 risk score
